from django.test import TestCase
from rest_framework.test import APIClient

from core.models import AsyncOperation, OperationDispatchOutbox
from core.tasks import execute_operation
from users.models import User

from .models import EvaluationDataset, EvaluationRun


class EvaluationOperationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='evaluation-admin',
            email='evaluation-admin@example.com',
            password='test-password',
            is_staff=True,
        )
        self.dataset = EvaluationDataset.objects.create(
            name='合成离线评估数据集',
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = '/api/v1/evaluation-runs/'

    def test_create_requires_operation_reason(self):
        response = self.client.post(
            self.url,
            {'dataset': self.dataset.id},
            format='json',
            HTTP_IDEMPOTENCY_KEY='evaluation-without-reason',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['code'], 'operation_reason_required')
        self.assertFalse(EvaluationRun.objects.exists())

    def test_create_is_idempotent_and_dispatch_contains_only_operation_id(self):
        payload = {'dataset': self.dataset.id, 'operation_reason': '验证候选配置'}
        first = self.client.post(
            self.url,
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='evaluation-idempotent',
        )
        second = self.client.post(
            self.url,
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='evaluation-idempotent',
        )

        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(second.status_code, 202, second.data)
        self.assertEqual(first.data['operation_id'], second.data['operation_id'])
        self.assertEqual(EvaluationRun.objects.count(), 1)
        operation = AsyncOperation.objects.get(id=first.data['operation_id'])
        run = EvaluationRun.objects.get()
        self.assertEqual(run.operation_id, operation.id)
        dispatch = OperationDispatchOutbox.objects.get(operation=operation)
        self.assertEqual(dispatch.payload, {'operation_id': str(operation.id)})
        self.assertEqual(operation.metadata['operation_reason'], '验证候选配置')

    def test_handler_reloads_run_and_completes_public_operation(self):
        response = self.client.post(
            self.url,
            {'dataset': self.dataset.id, 'operation_reason': '运行规则评估'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='evaluation-execute',
        )
        self.assertEqual(response.status_code, 202, response.data)

        result = execute_operation.run(response.data['operation_id'])

        operation = AsyncOperation.objects.get(id=response.data['operation_id'])
        run = EvaluationRun.objects.get(operation=operation)
        self.assertEqual(operation.status, AsyncOperation.Status.SUCCEEDED)
        self.assertEqual(operation.result_type, 'EvaluationRun')
        self.assertEqual(run.status, EvaluationRun.Status.SUCCEEDED)
        self.assertEqual(result['status'], AsyncOperation.Status.SUCCEEDED)
