import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Lock
from types import SimpleNamespace

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.response import Response

from staff_admin.idempotency import (
    StaffIdempotencyConflict,
    StaffOperationInProgress,
    _claim_body,
    run_staff_idempotent,
)
from staff_admin.models import AdminIdempotencyRecord, StaffAccount


class StaffIdempotencyExpiryTests(TestCase):
    def setUp(self):
        self.staff = StaffAccount.objects.create_account(
            email='idempotency-admin@example.com',
            password='staff-pass-123',
            display_name='Idempotency Admin',
            status=StaffAccount.Status.ACTIVE,
        )

    def request(self, data, key='admin-operation'):
        return SimpleNamespace(
            user=self.staff,
            data=data,
            headers={'Idempotency-Key': key},
        )

    def test_expired_completed_key_can_be_reused_for_a_different_request(self):
        old = AdminIdempotencyRecord.objects.create(
            account=self.staff,
            scope='staff-test',
            key='admin-operation',
            request_hash='old-fingerprint',
            response_status=201,
            response_body={'old': True},
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        calls = []

        response = run_staff_idempotent(
            self.request({'new': True}),
            'staff-test',
            lambda: calls.append('called') or Response({'new': True}, status=202),
        )

        current = AdminIdempotencyRecord.objects.get(
            account=self.staff, scope='staff-test', key='admin-operation'
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(calls, ['called'])
        self.assertNotEqual(current.id, old.id)

    def test_unexpired_key_with_different_fingerprint_still_conflicts(self):
        AdminIdempotencyRecord.objects.create(
            account=self.staff,
            scope='staff-test',
            key='admin-operation',
            request_hash='different-fingerprint',
            response_status=201,
            response_body={'old': True},
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaises(StaffIdempotencyConflict):
            run_staff_idempotent(
                self.request({'new': True}),
                'staff-test',
                lambda: Response({'unexpected': True}),
            )

    def test_active_database_claim_rejects_duplicate_before_callback(self):
        request = self.request({'value': 1})
        from staff_admin.idempotency import _fingerprint

        AdminIdempotencyRecord.objects.create(
            account=self.staff,
            scope='staff-test',
            key='admin-operation',
            request_hash=_fingerprint(request),
            response_status=102,
            response_body=_claim_body(
                status='pending',
                claim_token='current-owner',
                lease_expires_at=timezone.now() + timedelta(minutes=1),
            ),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaises(StaffOperationInProgress):
            run_staff_idempotent(request, 'staff-test', lambda: Response({'unexpected': True}))


class StaffIdempotencyConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.staff = StaffAccount.objects.create_account(
            email='concurrent-admin@example.com',
            password='staff-pass-123',
            display_name='Concurrent Admin',
            status=StaffAccount.Status.ACTIVE,
        )

    def test_concurrent_requests_execute_staff_side_effect_once(self):
        worker_count = 12
        barrier = Barrier(worker_count)
        callback_lock = Lock()
        callback_calls = []

        def worker(index):
            close_old_connections()
            try:
                account = StaffAccount.objects.get(pk=self.staff.pk)
                request = SimpleNamespace(
                    user=account,
                    data={'value': 1},
                    headers={'Idempotency-Key': 'staff-concurrent-key'},
                )
                barrier.wait(timeout=5)

                def callback():
                    with callback_lock:
                        callback_calls.append(index)
                    time.sleep(0.15)
                    return Response({'ok': True}, status=201)

                try:
                    return run_staff_idempotent(request, 'staff-concurrent-test', callback).status_code
                except StaffOperationInProgress:
                    return 409
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            outcomes = list(pool.map(worker, range(worker_count)))

        self.assertEqual(len(callback_calls), 1)
        self.assertTrue(all(status in (201, 409) for status in outcomes))
        record = AdminIdempotencyRecord.objects.get(
            account=self.staff,
            scope='staff-concurrent-test',
            key='staff-concurrent-key',
        )
        self.assertEqual(record.response_body, {'ok': True})
