from asgiref.sync import async_to_sync
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time
from types import SimpleNamespace
from django.db import close_old_connections
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.test import APIClient

from chat.middleware import JwtAuthMiddleware
from core.uploads import validate_uploaded_file
from core.cache_policy import POLICIES, jittered_ttl
from core.idempotency import OperationInProgress, run_idempotent
from core.models import IdempotencyRecord
from users.models import User


class WebSocketTicketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ticket-owner', email='ticket-owner@example.com', password='pass12345')
        self.peer = User.objects.create_user(username='ticket-peer', email='ticket-peer@example.com', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_ticket_is_scoped_and_single_use(self):
        response = self.client.post('/api/v1/ws-tickets/', {'scope': 'chat', 'resource_id': str(self.peer.id)}, format='json')
        self.assertEqual(response.status_code, 201)
        ticket = response.data['ticket']
        seen = []

        async def inner(scope, receive, send):
            seen.append(scope['user'])

        async def run_twice():
            middleware = JwtAuthMiddleware(inner)
            scope = {'path': f'/ws/chat/{self.peer.id}/', 'query_string': f'ticket={ticket}'.encode()}
            await middleware(dict(scope), None, None)
            await middleware(dict(scope), None, None)

        async_to_sync(run_twice)()
        self.assertEqual(seen[0].id, self.user.id)
        self.assertIsInstance(seen[1], AnonymousUser)


class UploadBoundaryTests(TestCase):
    def test_rejects_extension_signature_mismatch(self):
        uploaded = SimpleUploadedFile('resume.pdf', b'not a pdf', content_type='application/pdf')
        with self.assertRaises(ValidationError):
            validate_uploaded_file(uploaded, allowed_extensions={'.pdf'}, max_bytes=1024)

    def test_accepts_valid_png_signature(self):
        uploaded = SimpleUploadedFile('avatar.png', b'\x89PNG\r\n\x1a\n' + b'content', content_type='image/png')
        self.assertEqual(validate_uploaded_file(uploaded, allowed_extensions={'.png'}, max_bytes=1024), '.png')


class IdempotencyClaimTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='idem-user', email='idem@example.com', password='pass12345')

    def request(self, key='same-key'):
        return SimpleNamespace(
            user=self.user,
            data={'value': 1},
            headers={'Idempotency-Key': key},
        )

    def test_completed_operation_replays_without_running_callback(self):
        calls = []
        first = run_idempotent(self.request(), 'test', lambda: calls.append(1) or Response({'ok': True}, status=201))
        second = run_idempotent(self.request(), 'test', lambda: calls.append(2) or Response({'ok': False}))
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(calls, [1])
        self.assertEqual(second['X-Idempotent-Replay'], 'true')

    def test_active_claim_returns_operation_in_progress(self):
        IdempotencyRecord.objects.create(
            user=self.user,
            scope='test',
            key='same-key',
            request_hash='48208f9428d64634bd8e28ff345bf0eab60d53c18fa2fbdb0b9bc1e84df2b5f6',
            status=IdempotencyRecord.Status.PENDING,
            lease_expires_at=timezone.now() + timedelta(minutes=1),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaises(OperationInProgress):
            run_idempotent(self.request(), 'test', lambda: Response({'unexpected': True}))

    def test_retryable_response_releases_claim_for_retry(self):
        first = run_idempotent(
            self.request(),
            'test',
            lambda: Response({'code': 'operation_busy', 'retryable': True}, status=409),
        )
        second = run_idempotent(
            self.request(),
            'test',
            lambda: Response({'ok': True}, status=202),
        )
        record = IdempotencyRecord.objects.get(user=self.user, scope='test', key='same-key')
        self.assertEqual(first.status_code, 409)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(record.status, IdempotencyRecord.Status.COMPLETED)


class IdempotencyConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='idem-concurrent', email='idem-concurrent@example.com', password='pass12345'
        )

    def test_concurrent_claims_execute_business_callback_once(self):
        worker_count = 24
        barrier = Barrier(worker_count)
        callback_lock = Lock()
        callback_calls = []

        def worker(index):
            close_old_connections()
            try:
                user = User.objects.get(id=self.user.id)
                request = SimpleNamespace(
                    user=user,
                    data={'value': 1},
                    headers={'Idempotency-Key': 'concurrent-key'},
                )
                barrier.wait(timeout=5)

                def callback():
                    with callback_lock:
                        callback_calls.append(index)
                    time.sleep(0.15)
                    return Response({'ok': True}, status=202)

                try:
                    response = run_idempotent(request, 'concurrent-test', callback)
                    return response.status_code
                except OperationInProgress:
                    return 409
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            outcomes = list(pool.map(worker, range(worker_count)))

        self.assertEqual(len(callback_calls), 1)
        self.assertTrue(all(status in (202, 409) for status in outcomes))
        record = IdempotencyRecord.objects.get(
            user=self.user, scope='concurrent-test', key='concurrent-key'
        )
        self.assertEqual(record.status, IdempotencyRecord.Status.COMPLETED)


class CachePolicyTests(TestCase):
    def test_ttl_jitter_stays_within_configured_window(self):
        policy = POLICIES['article_recommendations']
        samples = [jittered_ttl(policy) for _ in range(100)]
        self.assertGreaterEqual(min(samples), int(policy.ttl_seconds * 0.8))
        self.assertLessEqual(max(samples), int(policy.ttl_seconds * 1.2))
        self.assertGreater(len(set(samples)), 1)

# Create your tests here.
