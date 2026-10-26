from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .broker_dlq import DLQValidationError, inspect_queue, message_route, queue_target, replay_batch
from .models import AdminAuditEvent, AdminIdempotencyRecord, StaffAccount, StaffRole


def make_message(target, *, task='core.tasks.execute_operation', route=None):
    message = MagicMock()
    message.body = b'[["opaque-operation-id"],{},null]'
    message.content_type = 'application/json'
    message.content_encoding = 'utf-8'
    message.properties = {'correlation_id': 'stable-task-id'}
    message.headers = {'task': task, 'id': 'stable-task-id', 'argsrepr': 'PRIVATE',
                       'x-death': [{'queue': target.name, 'exchange': target.exchange.name,
                                    'routing-keys': [route or target.routing_key]}],
                       'x-delivery-count': 13}
    return message


class BrokerDLQProtocolTests(SimpleTestCase):
    def setUp(self):
        self.queue = settings.CELERY_RESUME_RENDER_QUEUE + '.dlq'
        self.target = queue_target(self.queue)

    def test_unknown_queue_never_connects(self):
        with patch('staff_admin.broker_dlq.broker_connection') as connection:
            with self.assertRaises(DLQValidationError):
                inspect_queue('arbitrary.queue')
            connection.assert_not_called()

    def test_strict_route_and_task_validation(self):
        message = make_message(self.target)
        self.assertEqual(message_route(message, self.target), self.target.routing_key)
        for change, code in (
            ({'task': 'evil.task'}, 'unsupported_durable_task'),
            ({'x-death': []}, 'missing_death_history'),
            ({'x-death': [{'queue': 'other'}]}, 'source_queue_mismatch'),
            ({'x-death': [{'queue': self.target.name, 'exchange': 'evil'}]}, 'source_exchange_mismatch'),
            ({'x-death': [{'queue': self.target.name, 'exchange': self.target.exchange.name,
                          'routing-keys': ['wrong']}]}, 'original_route_mismatch'),
        ):
            with self.subTest(code=code):
                row = make_message(self.target)
                row.headers.update(change)
                with self.assertRaisesRegex(DLQValidationError, code):
                    message_route(row, self.target)

    def test_non_json_and_oversize_are_retained(self):
        row = make_message(self.target)
        row.content_type = 'application/x-python-serialize'
        with self.assertRaisesRegex(DLQValidationError, 'unsupported_content_type'):
            message_route(row, self.target)
        row.content_type = 'application/json'
        row.body = b'x' * 2_000_001
        with self.assertRaisesRegex(DLQValidationError, 'message_too_large'):
            message_route(row, self.target)

    def _run(self, messages, *, dry_run=False, publish_error=None, receipt_error=None):
        connection = MagicMock()
        channel = connection.__enter__.return_value.channel.return_value
        receipt = MagicMock(side_effect=receipt_error)
        with patch('staff_admin.broker_dlq.broker_connection', return_value=connection), \
             patch('staff_admin.broker_dlq.Queue') as queue, \
             patch('staff_admin.broker_dlq.Producer') as producer:
            queue.return_value.get.side_effect = [*messages, None]
            producer.return_value.publish.side_effect = publish_error
            result = replay_batch(self.queue, limit=10, dry_run=dry_run, record_confirm=receipt)
            channel.close.assert_called_once()
            channel.exchange_declare.assert_called_once_with(
                exchange=self.target.exchange.name, type=self.target.exchange.type, passive=True)
            return result, producer.return_value, receipt

    def test_dry_run_never_publishes_or_acks_or_exposes_private_body(self):
        message = make_message(self.target)
        result, producer, receipt = self._run([message], dry_run=True)
        self.assertEqual(result['retained'], 1)
        self.assertEqual(result['messages'][0]['status'], 'eligible')
        producer.publish.assert_not_called()
        receipt.assert_not_called()
        message.ack.assert_not_called()
        self.assertNotIn('PRIVATE', str(result))
        self.assertNotIn('opaque-operation-id', str(result))

    def test_confirm_then_receipt_then_ack(self):
        message = make_message(self.target)
        order = []
        message.ack.side_effect = lambda: order.append('ack')
        connection = MagicMock()
        with patch('staff_admin.broker_dlq.broker_connection', return_value=connection), \
             patch('staff_admin.broker_dlq.Queue') as queue, \
             patch('staff_admin.broker_dlq.Producer') as producer:
            queue.return_value.get.side_effect = [message, None]
            producer.return_value.publish.side_effect = lambda *a, **kw: order.append('confirm')
            result = replay_batch(self.queue, limit=1, dry_run=False,
                                  record_confirm=lambda summary: order.append('receipt'))
            kwargs = producer.return_value.publish.call_args.kwargs
            self.assertTrue(kwargs['mandatory'])
            self.assertFalse(kwargs['retry'])
            self.assertEqual(kwargs['delivery_mode'], 2)
            self.assertNotIn('x-death', kwargs['headers'])
            self.assertEqual(kwargs['headers']['id'], 'stable-task-id')
        self.assertEqual(order, ['confirm', 'receipt', 'ack'])
        self.assertEqual(result['replayed'], 1)

    def test_failed_publish_or_receipt_never_acks(self):
        for failure in ('publish', 'receipt'):
            with self.subTest(failure=failure):
                message = make_message(self.target)
                result, _, _ = self._run([message], publish_error=RuntimeError() if failure == 'publish' else None,
                                         receipt_error=RuntimeError() if failure == 'receipt' else None)
                self.assertFalse(result['complete'])
                self.assertEqual(result['retained'], 1)
                message.ack.assert_not_called()

    def test_invalid_message_does_not_block_next_valid_message(self):
        bad = make_message(self.target, task='legacy.unsafe')
        good = make_message(self.target)
        result, _, _ = self._run([bad, good])
        self.assertEqual((result['retained'], result['replayed']), (1, 1))
        bad.ack.assert_not_called()
        good.ack.assert_called_once()


class BrokerDLQAdminTests(TestCase):
    def setUp(self):
        self.role = StaffRole.objects.create(slug='dlq-test', name='队列测试', permissions=['platform_events.view', 'platform_events.replay'])
        self.staff = StaffAccount.objects.create_account(email='dlq@example.test', password='test-only-pass', display_name='测试', status='active')
        self.staff.roles.add(self.role)
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.url = '/api/admin/v1/operations/broker-dlq/'
        self.body = {'queue': settings.CELERY_RESUME_RENDER_QUEUE + '.dlq', 'limit': 5, 'dry_run': True, 'operation_reason': '合成测试'}

    def post(self, body=None, key='dlq-test-key'):
        return self.client.post(self.url, body or self.body, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def test_view_permission_cannot_replay(self):
        self.role.permissions = ['platform_events.view']
        self.role.save()
        with patch('staff_admin.broker_views.replay_batch') as replay:
            self.assertEqual(self.post().status_code, 403)
            replay.assert_not_called()

    def test_requires_reason_and_key(self):
        self.assertEqual(self.post({**self.body, 'operation_reason': ''}).status_code, 400)
        self.assertEqual(self.client.post(self.url, self.body, format='json').status_code, 400)

    def test_invalid_batch_or_queue_never_touches_broker(self):
        for extra in ({'limit': 0}, {'limit': 101}, {'limit': True}, {'dry_run': 'false'}, {'queue': 'other'}, {'queue': []}):
            with self.subTest(extra=extra), patch('staff_admin.broker_views.replay_batch') as replay:
                self.assertEqual(self.post({**self.body, **extra}).status_code, 400)
                replay.assert_not_called()

    def test_replay_same_key_has_one_side_effect_and_audit(self):
        def batch(*args, record_confirm, **kwargs):
            record_confirm({'body_hash': 'safe-hash', 'routing_key': 'resume.render'})
            return {'queue': self.body['queue'], 'examined': 1, 'replayed': 1, 'retained': 0}
        with patch('staff_admin.broker_views.replay_batch', side_effect=batch) as replay:
            first = self.post()
            second = self.post()
            self.assertEqual((first.status_code, second.status_code), (200, 200))
            self.assertEqual(second['X-Idempotent-Replay'], 'true')
            replay.assert_called_once()
        self.assertEqual(AdminAuditEvent.objects.count(), 3)
        self.assertEqual(AdminAuditEvent.objects.get(action='broker_dlq.publish_confirmed').operation_reason, '合成测试')

    def test_same_key_different_payload_conflicts(self):
        with patch('staff_admin.broker_views.replay_batch', return_value={'replayed': 0}):
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post({**self.body, 'limit': 6}).status_code, 409)

    def test_broker_errors_are_redacted_and_audited(self):
        with patch('staff_admin.broker_views.replay_batch', side_effect=RuntimeError('amqp://SECRET')):
            result = self.post()
        self.assertEqual(result.status_code, 503)
        self.assertNotIn('SECRET', str(result.data))
        self.assertTrue(AdminAuditEvent.objects.filter(action='broker_dlq.replay_failed').exists())

    def test_failed_final_receipt_cannot_advance_to_next_batch(self):
        with patch('staff_admin.broker_views.replay_batch', return_value={'replayed': 1}) as replay, \
             patch('staff_admin.idempotency._finish_claim', return_value=False):
            self.assertEqual(self.post().status_code, 200)
            replay.assert_called_once()
        record = AdminIdempotencyRecord.objects.get()
        record.response_body['_ifaceoff_idempotency']['lease_expires_at'] = '2000-01-01T00:00:00Z'
        record.save()
        with patch('staff_admin.broker_views.replay_batch') as replay:
            result = self.post()
            self.assertEqual(result.status_code, 409)
            self.assertEqual(result.data['code'], 'broker_replay_outcome_uncertain')
            replay.assert_not_called()

    def test_retry_after_broker_failure_requires_audit_reconciliation(self):
        with patch('staff_admin.broker_views.replay_batch', side_effect=RuntimeError()):
            self.assertEqual(self.post().status_code, 503)
        with patch('staff_admin.broker_views.replay_batch') as replay:
            self.assertEqual(self.post().status_code, 409)
            replay.assert_not_called()

    def test_read_is_passive_and_requires_valid_queue(self):
        with patch('staff_admin.broker_views.inspect_queue', return_value={'ready': 0}) as inspect:
            result = self.client.get(self.url, {'queue': self.body['queue']})
        self.assertEqual(result.status_code, 200)
        inspect.assert_called_once_with(self.body['queue'])
