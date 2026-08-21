import json
from uuid import UUID

from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from users.models import User

from .admission import CapacityRejected
from .middleware import (
    RequestIdMiddleware,
    get_current_correlation_id,
    get_current_trace_id,
)
from .operations import create_operation


class CorrelationIdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='correlation-user',
            email='correlation@example.com',
            password='test-password',
        )

    def test_middleware_propagates_safe_ids_into_operation(self):
        correlation_id = '9aa0dff6-e6f1-4c6d-bfd4-d61541d1fd89'

        def view(request):
            operation = create_operation(
                user=self.user,
                operation_type='test.correlation',
                source_app='core',
                source_model='Fixture',
                source_id='1',
                title='Correlation fixture',
            )
            return JsonResponse({
                'operation_id': str(operation.id),
                'correlation_id': str(operation.correlation_id),
                'trace_id': operation.trace_id,
            })

        request = RequestFactory().get(
            '/api/v2/test',
            HTTP_X_REQUEST_ID='request-123',
            HTTP_X_CORRELATION_ID=correlation_id,
            HTTP_X_TRACE_ID='trace-123',
        )
        response = RequestIdMiddleware(view)(request)
        payload = json.loads(response.content)
        self.assertEqual(payload['correlation_id'], correlation_id)
        self.assertEqual(payload['trace_id'], 'trace-123')
        self.assertEqual(response['X-Correlation-Id'], correlation_id)
        self.assertEqual(response['X-Trace-Id'], 'trace-123')
        self.assertEqual(get_current_correlation_id(), '')
        self.assertEqual(get_current_trace_id(), '')

    def test_invalid_external_ids_are_replaced(self):
        request = RequestFactory().get(
            '/',
            HTTP_X_REQUEST_ID='invalid id with spaces',
            HTTP_X_CORRELATION_ID='not-a-uuid',
            HTTP_X_TRACE_ID='bad trace value',
        )
        response = RequestIdMiddleware(lambda _request: JsonResponse({'ok': True}))(request)
        UUID(response['X-Correlation-Id'])
        self.assertNotEqual(response['X-Request-Id'], 'invalid id with spaces')
        self.assertNotEqual(response['X-Trace-Id'], 'bad trace value')

    def test_capacity_error_uses_stable_contract(self):
        exc = CapacityRejected(scope='resume.user', retry_after_ms=2500)
        self.assertEqual(exc.status_code, 429)
        self.assertEqual(exc.detail['code'], 'capacity_limited')
        self.assertEqual(int(exc.detail['retry_after_ms']), 2500)

        dependency = CapacityRejected(
            scope='resume.coordination',
            retry_after_ms=2000,
            overloaded=True,
            error_code='dependency_unavailable',
        )
        self.assertEqual(dependency.status_code, 503)
        self.assertEqual(dependency.detail['code'], 'dependency_unavailable')
