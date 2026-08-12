from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.events import enqueue_integration_event
from core.models import AsyncOperation, IntegrationOutbox, OperationDispatchOutbox
from core.operations import create_operation, create_operation_with_dispatch
from users.models import User

from .models import StaffAccount, StaffRole


class PlatformReliabilityAdminTests(TestCase):
    def setUp(self):
        role = StaffRole.objects.create(
            slug='platform-reliability-test',
            name='Platform Reliability Test',
            permissions=['*'],
        )
        self.staff = StaffAccount.objects.create_account(
            email='reliability-admin@example.com',
            password='staff-pass-123',
            display_name='Reliability Admin',
            status=StaffAccount.Status.ACTIVE,
            recovery_codes_confirmed_at=timezone.now(),
        )
        self.staff.roles.add(role)
        self.user = User.objects.create_user(
            username='operation-owner',
            email='operation-owner@example.com',
            password='pass12345',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_platform_events_separates_database_dead_rows_from_broker_dlq(self):
        event = enqueue_integration_event(
            event_type='test.event',
            producer='tests',
            aggregate_type='TestAggregate',
            aggregate_id='aggregate-1',
            payload={'record_id': 'aggregate-1'},
        )
        IntegrationOutbox.objects.filter(pk=event.pk).update(
            status=IntegrationOutbox.Status.DEAD,
            attempts=12,
            last_error='ConnectionError: amqp://secret@example.invalid',
        )
        operation = create_operation_with_dispatch(
            user=self.user,
            operation_type='test.dispatch',
            source_app='tests',
            source_model='Input',
            source_id='input-1',
            title='Dispatch test',
            queue='ifaceoff.v2.documents',
            routing_key='documents',
            kick_publisher=False,
        )
        OperationDispatchOutbox.objects.filter(operation=operation).update(
            status=OperationDispatchOutbox.Status.DEAD,
            attempts=12,
            last_error='BrokerError: should-not-leak',
        )

        response = self.client.get('/api/admin/v1/operations/events/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['database_outbox_dead_letters']), 1)
        self.assertEqual(len(response.data['operation_dispatch_dead_letters']), 1)
        self.assertNotIn('last_error', response.data['database_outbox_dead_letters'][0])
        self.assertNotIn('last_error', response.data['operation_dispatch_dead_letters'][0])
        self.assertFalse(response.data['broker_dead_letters']['replay_supported'])
        self.assertEqual(response.data['broker_dead_letters']['source'], 'rabbitmq')

    def test_database_outbox_replay_is_idempotent_and_does_not_claim_broker_replay(self):
        event = enqueue_integration_event(
            event_type='test.replay',
            producer='tests',
            aggregate_type='TestAggregate',
            aggregate_id='aggregate-2',
            payload={'record_id': 'aggregate-2'},
        )
        IntegrationOutbox.objects.filter(pk=event.pk).update(
            status=IntegrationOutbox.Status.DEAD,
            attempts=12,
        )
        payload = {'operation_reason': '验证 PostgreSQL Outbox 受控重放。'}

        first = self.client.post(
            f'/api/admin/v1/operations/events/{event.event_id}/replay/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='database-outbox-replay-once',
        )
        second = self.client.post(
            f'/api/admin/v1/operations/events/{event.event_id}/replay/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='database-outbox-replay-once',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second['X-Idempotent-Replay'], 'true')
        event.refresh_from_db()
        self.assertEqual(event.status, IntegrationOutbox.Status.PENDING)

    def test_reliability_policy_rejects_invalid_runtime_integer(self):
        response = self.client.post(
            '/api/admin/v1/reliability/',
            {
                'key': 'reliability-admission',
                'name': 'Admission',
                'config': {'lease_seconds': 'not-an-integer'},
                'operation_reason': '验证运行策略严格校验。',
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='invalid-runtime-policy',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_policy_value')

    def test_staff_cancel_uses_authoritative_operation_service(self):
        operation = create_operation(
            user=self.user,
            operation_type='test.cancel',
            source_app='tests',
            source_model='Input',
            source_id='cancel-1',
            title='Cancel test',
        )
        response = self.client.post(
            f'/api/admin/v1/tasks/{operation.pk}/cancel/',
            {'operation_reason': '验证管理端取消进入统一状态机。'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='cancel-operation-once',
        )

        self.assertEqual(response.status_code, 200)
        operation.refresh_from_db()
        self.assertEqual(operation.status, AsyncOperation.Status.CANCELED)
        self.assertIsNotNone(operation.completed_at)
        self.assertTrue(operation.events.filter(event_type='operation.canceled').exists())
