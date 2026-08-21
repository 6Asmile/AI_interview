import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.db import IntegrityError, OperationalError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from core.idempotency import request_fingerprint, run_idempotent
from core.events import (
    ConsumerInboxLeaseActive,
    _payload_hash,
    consume_event,
    enqueue_integration_event,
    register_event_handler,
)
from core.models import (
    AsyncOperation,
    ConsumerInbox,
    IdempotencyRecord,
    IntegrationOutbox,
    OperationDispatchOutbox,
)
from core.operation_registry import (
    OperationHandlerResult,
    register_operation_handler,
    unregister_operation_handler,
)
from core.operations import (
    OperationLeaseLost,
    append_operation_event,
    claim_operation,
    checkpoint_operation,
    complete_operation,
    create_operation,
    create_operation_with_dispatch,
    fail_operation,
    heartbeat_operation,
    recover_stale_operations,
    request_operation_cancel,
    request_operation_retry,
    start_operation,
)
from core.tasks import (
    execute_operation,
    publish_integration_outbox,
    publish_operation_dispatch_outbox,
)
from core.task_registry import register_operation as register_legacy_projection
from users.models import User


class OperationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='operation-owner',
            email='operation-owner@example.com',
            password='pass12345',
        )

    def create_operation(self, **overrides):
        values = {
            'user': self.user,
            'operation_type': 'tests.operation',
            'source_app': 'core',
            'source_model': 'Fixture',
            'source_id': str(uuid.uuid4()),
            'title': '测试异步操作',
            'input_type': 'fixture',
            'input_id': str(uuid.uuid4()),
        }
        values.update(overrides)
        return create_operation(**values)

    def create_dispatched_operation(self, **overrides):
        values = {
            'user': self.user,
            'operation_type': 'tests.operation',
            'source_app': 'core',
            'source_model': 'Fixture',
            'source_id': str(uuid.uuid4()),
            'title': '测试异步操作',
            'input_type': 'fixture',
            'input_id': str(uuid.uuid4()),
            'kick_publisher': False,
        }
        values.update(overrides)
        return create_operation_with_dispatch(**values)

    def test_same_source_can_create_multiple_operations_and_business_key_is_unique(self):
        source_id = str(uuid.uuid4())
        first = self.create_operation(source_id=source_id)
        second = self.create_operation(source_id=source_id, operation_type='tests.operation.again')
        self.assertNotEqual(first.pk, second.pk)

        key_hash = hashlib.sha256(b'operation-key').hexdigest()
        self.create_operation(
            operation_type='tests.unique',
            idempotency_key_hash=key_hash,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_operation(
                    operation_type='tests.unique',
                    idempotency_key_hash=key_hash,
                )

    def test_legacy_projection_is_disambiguated_and_has_explicit_active_lease(self):
        source_id = str(uuid.uuid4())
        authoritative = self.create_operation(
            operation_type='tests.authoritative',
            source_app='video_uploads',
            source_model='FileUploadTask',
            source_id=source_id,
        )
        projection = register_legacy_projection(
            user=self.user,
            operation_type='video_upload',
            source_app='video_uploads',
            source_model='FileUploadTask',
            source_id=source_id,
            title='旧上传投影',
            status='processing',
        )
        repeated = register_legacy_projection(
            user=self.user,
            operation_type='video_upload',
            source_app='video_uploads',
            source_model='FileUploadTask',
            source_id=source_id,
            title='旧上传投影',
            status='processing',
        )
        self.assertNotEqual(authoritative.pk, projection.pk)
        self.assertEqual(repeated.pk, projection.pk)
        self.assertEqual(projection.status, AsyncOperation.Status.RUNNING)
        self.assertEqual(projection.lease_owner, 'legacy-projection')
        self.assertIsNotNone(projection.lease_expires_at)

        request_operation_cancel(projection.pk, user=self.user)
        after_cancel = register_legacy_projection(
            user=self.user,
            operation_type='video_upload',
            source_app='video_uploads',
            source_model='FileUploadTask',
            source_id=source_id,
            title='旧上传投影',
            status='processing',
        )
        self.assertEqual(after_cancel.status, AsyncOperation.Status.CANCELED)

    def test_database_state_constraints_reject_invalid_rows(self):
        values = {
            'user': self.user,
            'operation_type': 'tests.constraint',
            'source_app': 'core',
            'source_model': 'Fixture',
            'source_id': str(uuid.uuid4()),
            'title': '约束测试',
        }
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsyncOperation.objects.create(status=AsyncOperation.Status.RUNNING, **values)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsyncOperation.objects.create(
                    status=AsyncOperation.Status.FAILED,
                    source_id=str(uuid.uuid4()),
                    **{key: value for key, value in values.items() if key != 'source_id'},
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsyncOperation.objects.create(
                    progress=101,
                    source_id=str(uuid.uuid4()),
                    **{key: value for key, value in values.items() if key != 'source_id'},
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsyncOperation.objects.create(
                    attempt_count=6,
                    max_attempts=5,
                    source_id=str(uuid.uuid4()),
                    **{key: value for key, value in values.items() if key != 'source_id'},
                )

    def test_dispatch_payload_is_forced_to_authoritative_id(self):
        operation = self.create_operation()
        dispatch = OperationDispatchOutbox.objects.create(
            operation=operation,
            task_name='untrusted.task',
            payload={'resume': 'private text'},
            available_at=timezone.now(),
        )
        self.assertEqual(dispatch.task_name, 'core.tasks.execute_operation')
        self.assertEqual(dispatch.payload, {'operation_id': str(operation.pk)})

    def test_domain_queue_uses_its_declared_routing_key(self):
        operation = self.create_dispatched_operation(queue=settings.CELERY_CAREER_QUEUE)
        dispatch = operation.dispatches.get()
        configured = next(
            queue for queue in settings.CELERY_TASK_QUEUES
            if queue.name == settings.CELERY_CAREER_QUEUE
        )
        self.assertEqual(dispatch.routing_key, configured.routing_key)

    def test_claim_heartbeat_and_complete_use_fencing(self):
        operation = self.create_dispatched_operation()
        claim = claim_operation(operation.pk, worker_id='worker-a', lease_seconds=60)
        self.assertIsNotNone(claim)
        self.assertIsNone(claim_operation(operation.pk, worker_id='worker-b', lease_seconds=60))
        start_operation(claim)
        self.assertTrue(heartbeat_operation(claim, lease_seconds=90))
        checkpointed = checkpoint_operation(
            claim,
            progress=35,
            payload={'stage': 'loaded'},
        )
        self.assertEqual(checkpointed.progress, 35)
        completed = complete_operation(
            claim,
            result_type='fixture',
            result_id='result-1',
            result={
                'count': 1,
                'resume': 'private body',
                'credentials': {'access_token': 'private-token'},
            },
        )
        self.assertEqual(completed.status, AsyncOperation.Status.SUCCEEDED)
        self.assertEqual(completed.result_json, {'count': 1, 'credentials': {}})
        self.assertIsNotNone(completed.completed_at)
        self.assertEqual(
            completed.events.get(event_type='operation.progress').payload['progress'],
            35,
        )

    def test_claim_stops_at_attempt_limit_without_violating_constraint(self):
        operation = self.create_dispatched_operation(max_attempts=1)
        AsyncOperation.objects.filter(pk=operation.pk).update(attempt_count=1)

        self.assertIsNone(claim_operation(operation.pk, worker_id='too-late-worker'))
        operation.refresh_from_db()
        self.assertEqual(operation.status, AsyncOperation.Status.FAILED)
        self.assertEqual(operation.attempt_count, 1)
        self.assertEqual(operation.error_code, 'operation_attempts_exhausted')
        self.assertIsNotNone(operation.completed_at)

    def test_immediate_cancel_fences_the_old_worker(self):
        operation = self.create_dispatched_operation()
        claim = claim_operation(operation.pk, worker_id='worker-a', lease_seconds=60)
        start_operation(claim)

        canceled = request_operation_cancel(operation.pk, user=self.user)
        self.assertEqual(canceled.status, AsyncOperation.Status.CANCELED)
        self.assertGreater(canceled.fencing_token, claim.fencing_token)
        with self.assertRaises(OperationLeaseLost):
            complete_operation(claim, result={'late': True})

    def test_retry_appends_dispatch_generation_and_keeps_history(self):
        operation = self.create_dispatched_operation()
        claim = claim_operation(operation.pk, worker_id='worker-a')
        start_operation(claim)
        retrying = fail_operation(
            claim,
            error_code='temporary_provider_error',
            retryable=True,
            retry_after_seconds=0,
        )
        self.assertEqual(retrying.status, AsyncOperation.Status.RETRYING)
        self.assertEqual(
            list(operation.dispatches.order_by('fencing_token').values_list('fencing_token', flat=True)),
            [0, 1],
        )

        retrying.status = AsyncOperation.Status.FAILED
        retrying.completed_at = timezone.now()
        retrying.retryable = True
        retrying.save(update_fields=['status', 'completed_at', 'retryable', 'updated_at'])
        request_operation_retry(operation.pk, user=self.user)
        self.assertEqual(
            list(operation.dispatches.order_by('fencing_token').values_list('fencing_token', flat=True)),
            [0, 1, 2],
        )

    def test_specialized_operation_can_retry_without_generic_dispatch(self):
        operation = self.create_operation(operation_type='interview.agent.execution')
        claim = claim_operation(operation.pk, worker_id='agent-worker')
        start_operation(claim)
        retrying = fail_operation(
            claim,
            error_code='provider_timeout',
            retryable=True,
            retry_after_seconds=0,
            dispatch_retry=False,
        )
        self.assertEqual(retrying.status, AsyncOperation.Status.RETRYING)
        self.assertFalse(operation.dispatches.exists())

    def test_recovery_requeues_generic_operation_and_fences_expired_claim(self):
        operation = self.create_dispatched_operation()
        claim = claim_operation(operation.pk, worker_id='stale-worker')
        AsyncOperation.objects.filter(pk=operation.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        outcome = recover_stale_operations()
        operation.refresh_from_db()
        self.assertEqual(outcome['recovered'], 1)
        self.assertEqual(operation.status, AsyncOperation.Status.RETRYING)
        self.assertEqual(operation.dispatches.count(), 2)
        with self.assertRaises(OperationLeaseLost):
            complete_operation(claim, result={'late': True})

    def test_registered_handler_is_executed_from_operation_id_only(self):
        operation_type = f'tests.handler.{uuid.uuid4().hex}'
        seen = []

        def handler(context):
            current = context.get_operation()
            seen.append((context.operation_id, current.input_id, context.heartbeat()))
            return OperationHandlerResult(
                result_type='fixture',
                result_id='handler-result',
                result={'quality': 'ok'},
            )

        register_operation_handler(operation_type, handler)
        try:
            operation = self.create_dispatched_operation(operation_type=operation_type)
            result = execute_operation.run(str(operation.pk))
        finally:
            unregister_operation_handler(operation_type, handler)

        operation.refresh_from_db()
        self.assertEqual(result['status'], AsyncOperation.Status.SUCCEEDED)
        self.assertEqual(operation.result_id, 'handler-result')
        self.assertEqual(seen, [(operation.pk, operation.input_id, True)])

    @patch('core.tasks.execute_operation.apply_async')
    def test_dispatch_publisher_sends_only_operation_id(self, apply_async):
        apply_async.return_value = SimpleNamespace(id='celery-task-1')
        operation = self.create_dispatched_operation()
        result = publish_operation_dispatch_outbox.run()

        self.assertEqual(result['published'], 1)
        args = apply_async.call_args.kwargs['args']
        self.assertEqual(args, [str(operation.pk)])
        self.assertEqual(len(args), 1)
        dispatch = operation.dispatches.get()
        self.assertEqual(dispatch.status, OperationDispatchOutbox.Status.PUBLISHED)


class OperationClaimConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(
            username='operation-concurrent',
            email='operation-concurrent@example.com',
            password='pass12345',
        )
        self.operation = create_operation(
            user=self.user,
            operation_type='tests.concurrent',
            source_app='core',
            source_model='Fixture',
            source_id=str(uuid.uuid4()),
            title='并发领取',
        )

    def test_competing_workers_obtain_at_most_one_live_claim(self):
        worker_count = 8
        barrier = Barrier(worker_count)

        def worker(index):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                for attempt in range(20):
                    try:
                        claim = claim_operation(
                            self.operation.pk,
                            worker_id=f'worker-{index}',
                            lease_seconds=60,
                        )
                        return claim.worker_id if claim else None
                    except OperationalError:
                        time.sleep(0.01 * (attempt + 1))
                return 'database_locked'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            outcomes = list(pool.map(worker, range(worker_count)))

        winners = [outcome for outcome in outcomes if outcome and outcome != 'database_locked']
        self.assertEqual(len(winners), 1)
        self.operation.refresh_from_db()
        self.assertEqual(self.operation.status, AsyncOperation.Status.CLAIMED)
        self.assertEqual(self.operation.attempt_count, 1)


class OperationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='operation-api-owner',
            email='operation-api-owner@example.com',
            password='pass12345',
        )
        self.other_user = User.objects.create_user(
            username='operation-api-other',
            email='operation-api-other@example.com',
            password='pass12345',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_operation(self, **overrides):
        values = {
            'user': self.user,
            'operation_type': 'tests.api',
            'source_app': 'core',
            'source_model': 'Fixture',
            'source_id': str(uuid.uuid4()),
            'title': 'API 操作',
            'kick_publisher': False,
        }
        values.update(overrides)
        return create_operation_with_dispatch(**values)

    def test_detail_and_events_are_owner_scoped_and_cursor_based(self):
        operation = self.create_operation()
        append_operation_event(operation.pk, 'operation.progress', payload={'progress': 40})

        detail = self.client.get(f'/api/v2/operations/{operation.pk}/')
        self.assertEqual(detail.status_code, 200)
        first_page = self.client.get(
            f'/api/v2/operations/{operation.pk}/events/?after_sequence=0&limit=1'
        )
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data['events'][0]['event_type'], 'operation.accepted')
        self.assertEqual(first_page.data['next_after_sequence'], 1)

        second_page = self.client.get(
            f'/api/v2/operations/{operation.pk}/events/?after_sequence=1&limit=1'
        )
        self.assertEqual(second_page.data['events'][0]['event_type'], 'operation.progress')
        self.assertEqual(second_page.data['events'][0]['progress'], 40)
        self.assertIn('occurred_at', second_page.data['events'][0])
        self.assertEqual(second_page.data['next_after_sequence'], 2)

        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(f'/api/v2/operations/{operation.pk}/').status_code, 404)
        self.assertEqual(
            self.client.get(f'/api/v2/operations/{operation.pk}/events/').status_code,
            404,
        )

    def test_retry_requires_idempotency_and_appends_new_dispatch(self):
        operation = self.create_operation()
        AsyncOperation.objects.filter(pk=operation.pk).update(
            status=AsyncOperation.Status.FAILED,
            retryable=True,
            completed_at=timezone.now(),
        )
        url = f'/api/v2/operations/{operation.pk}/retry/'
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400)

        response = self.client.post(
            url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='retry-operation-key',
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['operation_id'], str(operation.pk))
        self.assertEqual(operation.dispatches.count(), 2)
        self.assertEqual(response['X-Operation-Id'], str(operation.pk))

        replay = self.client.post(
            url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='retry-operation-key',
        )
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay['X-Idempotent-Replay'], 'true')
        self.assertEqual(operation.dispatches.count(), 2)

    def test_cancel_is_immediate_idempotent_and_cross_user_is_hidden(self):
        operation = self.create_operation()
        url = f'/api/v2/operations/{operation.pk}/cancel/'
        response = self.client.post(
            url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='cancel-operation-key',
        )
        self.assertEqual(response.status_code, 202)
        operation.refresh_from_db()
        self.assertEqual(operation.status, AsyncOperation.Status.CANCELED)
        self.assertIsNotNone(operation.completed_at)
        self.assertEqual(operation.dispatches.get().status, OperationDispatchOutbox.Status.CANCELED)

        self.client.force_authenticate(self.other_user)
        hidden = self.client.post(
            url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='other-user-key',
        )
        self.assertEqual(hidden.status_code, 404)

    def test_v1_retry_and_cancel_also_require_idempotency_key(self):
        failed = self.create_operation()
        AsyncOperation.objects.filter(pk=failed.pk).update(
            status=AsyncOperation.Status.FAILED,
            retryable=True,
            completed_at=timezone.now(),
        )
        self.assertEqual(
            self.client.post(f'/api/v1/tasks/{failed.pk}/retry/', {}, format='json').status_code,
            400,
        )
        pending = self.create_operation()
        self.assertEqual(
            self.client.post(f'/api/v1/tasks/{pending.pk}/cancel/', {}, format='json').status_code,
            400,
        )


class CoreIdempotencyContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='operation-idempotency',
            email='operation-idempotency@example.com',
            password='pass12345',
        )

    def request(self, *, data=None, key='idempotency-key', path='/api/v2/test/', files=None):
        return SimpleNamespace(
            user=self.user,
            data=data or {},
            headers={'Idempotency-Key': key},
            method='POST',
            path=path,
            FILES=files or {},
        )

    def test_synchronous_response_does_not_publish_fake_operation_id(self):
        response = run_idempotent(
            self.request(data={'value': 1}),
            'tests.sync',
            lambda: Response({'ok': True}, status=201),
        )
        self.assertNotIn('X-Operation-Id', response)
        replay = run_idempotent(
            self.request(data={'value': 1}),
            'tests.sync',
            lambda: Response({'unexpected': True}),
        )
        self.assertEqual(replay['X-Idempotent-Replay'], 'true')
        self.assertNotIn('X-Operation-Id', replay)

    def test_expired_completed_record_is_reclaimed_instead_of_replayed(self):
        first = run_idempotent(
            self.request(data={'version': 1}),
            'tests.expiry',
            lambda: Response({'version': 1}, status=201),
        )
        self.assertEqual(first.status_code, 201)
        IdempotencyRecord.objects.filter(user=self.user, scope='tests.expiry').update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        calls = []
        second = run_idempotent(
            self.request(data={'version': 2}),
            'tests.expiry',
            lambda: calls.append(True) or Response({'version': 2}, status=202),
        )
        self.assertEqual(second.status_code, 202)
        self.assertEqual(calls, [True])
        self.assertNotIn('X-Idempotent-Replay', second)

    def test_fingerprint_covers_method_path_scope_reason_and_upload_checksum(self):
        upload_a = SimpleUploadedFile('resume.pdf', b'AAAA', content_type='application/pdf')
        upload_b = SimpleUploadedFile('resume.pdf', b'BBBB', content_type='application/pdf')
        request_a = self.request(
            data={'operation_reason': '首次导入'},
            files={'file': upload_a},
        )
        request_b = self.request(
            data={'operation_reason': '首次导入'},
            files={'file': upload_b},
        )
        first = request_fingerprint(request_a, 'resume.import')
        self.assertNotEqual(first, request_fingerprint(request_b, 'resume.import'))
        self.assertNotEqual(first, request_fingerprint(request_a, 'resume.reparse'))
        request_a.method = 'PUT'
        self.assertNotEqual(first, request_fingerprint(request_a, 'resume.import'))
        self.assertEqual(upload_a.tell(), 0)


class ConsumerInboxLeaseTests(TestCase):
    def test_active_duplicate_is_rescheduled_instead_of_acknowledged(self):
        event_type = f'tests.inbox.{uuid.uuid4().hex}'
        consumer_name = f'tests-consumer-{uuid.uuid4().hex}'
        calls = []

        @register_event_handler(event_type, consumer_name)
        def handler(envelope):
            calls.append(envelope['event_id'])
            return {'handled': True}

        envelope = {
            'event_id': str(uuid.uuid4()),
            'event_type': event_type,
            'event_version': 1,
            'payload': {'aggregate_id': str(uuid.uuid4())},
        }
        ConsumerInbox.objects.create(
            consumer_name=consumer_name,
            event_id=envelope['event_id'],
            event_type=event_type,
            event_version=1,
            payload_hash=_payload_hash(envelope),
            status=ConsumerInbox.Status.PROCESSING,
            claim_token=uuid.uuid4(),
            lease_owner='first-worker',
            lease_expires_at=timezone.now() + timedelta(seconds=30),
            fencing_token=1,
        )

        with self.assertRaises(ConsumerInboxLeaseActive) as raised:
            consume_event(envelope)
        self.assertGreater(raised.exception.retry_after_ms, 0)
        self.assertEqual(calls, [])


class IntegrationEventContractTests(TestCase):
    @patch('core.tasks.consume_integration_event.apply_async')
    def test_publisher_uses_configured_event_queue_and_exchange(self, apply_async):
        event = enqueue_integration_event(
            event_type='tests.aggregate.changed',
            producer='tests',
            aggregate_type='Fixture',
            aggregate_id=uuid.uuid4(),
            payload={'fixture_id': str(uuid.uuid4()), 'status': 'ready'},
        )
        result = publish_integration_outbox.run()
        self.assertEqual(result['published'], 1)
        kwargs = apply_async.call_args.kwargs
        self.assertEqual(kwargs['queue'], settings.CELERY_EVENTS_QUEUE)
        self.assertEqual(kwargs['exchange'], settings.CELERY_EVENTS_EXCHANGE)
        self.assertEqual(kwargs['routing_key'], 'tests.aggregate.changed')
        event.refresh_from_db()
        self.assertEqual(event.status, IntegrationOutbox.Status.PUBLISHED)

    def test_nested_sensitive_event_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            enqueue_integration_event(
                event_type='tests.aggregate.changed',
                producer='tests',
                aggregate_type='Fixture',
                aggregate_id=uuid.uuid4(),
                payload={'nested': {'access_token': 'must-not-be-persisted'}},
            )
