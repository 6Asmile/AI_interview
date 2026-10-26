"""Real deterministic APIs, disposable database; no LLM/RAG calls or HTTP server."""
import math
import os
import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from users.models import User


class RateLimitIsolationTests(TestCase):
    """DRF identity/window contracts; not Redis atomicity or capacity evidence."""
    def setUp(self):
        from django.core.cache.backends.locmem import LocMemCache
        from rest_framework.test import APIRequestFactory
        from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
        self.factory = APIRequestFactory()
        self.cache = LocMemCache('evaluation-throttle-isolation', {})
        self.cache.clear()
        self.anon_type = type('EvaluationAnonThrottle', (AnonRateThrottle,), {'rate': '2/min', 'cache': self.cache})
        self.user_type = type('EvaluationUserThrottle', (UserRateThrottle,), {'rate': '2/min', 'cache': self.cache})

    def request(self, path='/', ip='192.0.2.1', user=None):
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get(path, REMOTE_ADDR=ip)
        request.user = user or AnonymousUser()
        return request

    def test_anonymous_routes_share_ip_budget_but_distinct_ips_do_not(self):
        for path in ('/auth/csrf/', '/other-read/'):
            self.assertTrue(self.anon_type().allow_request(self.request(path), None))
        self.assertFalse(self.anon_type().allow_request(self.request(), None))
        self.assertTrue(self.anon_type().allow_request(self.request(ip='192.0.2.2'), None))

    def test_authenticated_users_on_same_ip_have_separate_budgets(self):
        users = [User.objects.create_user(username=f'throttle-{i}', email=f'throttle-{i}@example.invalid') for i in range(2)]
        for _ in range(2):
            self.assertTrue(self.user_type().allow_request(self.request(user=users[0]), None))
        self.assertFalse(self.user_type().allow_request(self.request(user=users[0]), None))
        self.assertTrue(self.user_type().allow_request(self.request(user=users[1]), None))

    def test_window_expires_at_boundary(self):
        throttle = self.anon_type()
        throttle.timer = lambda: 0
        self.assertTrue(throttle.allow_request(self.request(), None))
        self.assertTrue(throttle.allow_request(self.request(), None))
        self.assertFalse(throttle.allow_request(self.request(), None))
        self.assertEqual(throttle.wait(), 60)
        throttle.timer = lambda: 60
        self.assertTrue(throttle.allow_request(self.request(), None))


@override_settings(CACHES={alias: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'measurement-' + alias}
                           for alias in ('default', 'coordination', 'realtime')})
class DeterministicApiMeasurements(TestCase):
    def setUp(self):
        from django.core.cache import caches
        from rest_framework.throttling import SimpleRateThrottle
        self.local_cache = caches['default']
        self.enterContext(patch.object(SimpleRateThrottle, 'cache', self.local_cache))
        self.client = APIClient()
        self.user = User.objects.create_user(username='evaluation-synthetic', email='evaluation@example.invalid', password='synthetic')
        self.client.force_authenticate(self.user)
        self.measurements = []

    def measure(self, name, action, check, transaction_counter=None):
        values = []
        completed_transactions = 0
        started_all = time.perf_counter()
        for _ in range(int(os.environ.get('IFACEOFF_MEASUREMENT_SAMPLES', '20'))):
            # Endpoint timing is independent of rate-limit throughput. Redis
            # contracts are evaluated separately, never claimed by this sample.
            self.local_cache.clear()
            started = time.perf_counter()
            response = action()
            values.append((time.perf_counter() - started) * 1000)
            check(response)
            if transaction_counter:
                completed_transactions += int(bool(transaction_counter(response)))
        elapsed_seconds = time.perf_counter() - started_all
        values.sort()
        self.measurements.append({'name': name, 'sample_count': len(values), 'evidence_level': 'isolated_api_client',
            'p50_ms': round(values[math.ceil(len(values) * .5) - 1], 3),
            'p95_ms': round(values[math.ceil(len(values) * .95) - 1], 3),
            'p99_ms': round(values[math.ceil(len(values) * .99) - 1], 3),
            'max_ms': round(values[-1], 3), 'elapsed_seconds': round(elapsed_seconds, 4),
            'sequential_request_rate_per_second': round(len(values) / elapsed_seconds, 3) if elapsed_seconds else None,
            'completed_business_transactions': completed_transactions,
            'business_transactions_per_second': round(completed_transactions / elapsed_seconds, 3) if transaction_counter and elapsed_seconds else None,
            'slo_passed': None})

    def test_resume_create_persists_canonical_snapshot(self):
        before = self.user.resumes.count()
        previous_count = [before]
        def check(response):
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['current_version']['schema_version'], '1.3.1')
            self.assertEqual(response.data['current_design_revision']['template_key'], 'ats-classic')
        self.measure('简历创建 API', lambda: self.client.post('/api/v2/resumes/', {'title': '量化合成简历', 'status': 'draft'}, format='json'), check,
            transaction_counter=lambda _response: self._count_resume_created(previous_count))

    def _count_resume_created(self, previous_count):
        current = self.user.resumes.count()
        created = current > previous_count[0]
        previous_count[0] = current
        return created

    def test_templates_return_six_curated_entries(self):
        def check(response):
            self.assertEqual(response.status_code, 200)
            payload = response.data
            entries = payload if isinstance(payload, list) else payload.get('results', payload.get('templates', []))
            self.assertEqual(len(entries), 6)
        self.measure('模板目录 API', lambda: self.client.get('/api/v2/resume-templates/'), check)

    def test_operations_do_not_leak_other_users(self):
        from core.operations import create_operation
        other = User.objects.create_user(username='evaluation-other', email='other@example.invalid', password='synthetic')
        operation = create_operation(user=other, operation_type='tests.operation', source_app='core', source_model='Fixture', source_id='synthetic', title='合成隔离任务')
        self.measure('跨用户 Operation 拒绝 API', lambda: self.client.get(f'/api/v2/operations/{operation.pk}/'), lambda response: self.assertEqual(response.status_code, 404))
