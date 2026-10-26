"""Synthetic regression tests: unrelated commands must not block interviews."""
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from core.admission import admit_expensive_operation, CapacityRejected, TokenDecision
from core.models import OperationDispatchOutbox, IntegrationOutbox
from core.operations import create_operation_with_dispatch, recover_stale_operations, claim_operation
from core.worker_roles import ROLE_QUEUES, worker_queues, worker_arguments, queue_for_scope
from users.models import User


class WorkerContractTests(SimpleTestCase):
    def test_roles_do_not_share_queues(self):
        queues = [q for role in ROLE_QUEUES for q in worker_queues(role)]
        self.assertEqual(len(queues), len(set(queues)))
        self.assertNotEqual(queue_for_scope('resume.quality'), queue_for_scope('interview.turn'))
        self.assertNotEqual(queue_for_scope('resume.preview'), queue_for_scope('media'))

    def test_solo_is_explicitly_serial(self):
        with self.assertRaises(ValueError):
            worker_arguments('agent', pool='solo', concurrency=2)
        self.assertIn(settings.CELERY_AGENT_QUEUE, worker_arguments('agent', pool='solo'))


class QueueRecoveryTests(TestCase):
    def setUp(self):
        # These cases isolate DB backlog routing, not a live Redis constructor.
        self.enterContext(patch('core.admission.get_redis_connection'))
        self.user = User.objects.create_user(username='queue-fixture', email='queue@example.test', password='test')
        self.request = SimpleNamespace(user=self.user, META={'REMOTE_ADDR': '127.0.0.1'})

    def operation(self, queue=None):
        return create_operation_with_dispatch(
            user=self.user, operation_type='test.isolation', source_app='core',
            source_model='Fixture', source_id='synthetic', title='合成隔离测试',
            queue=queue or settings.CELERY_RESUME_RENDER_QUEUE, kick_publisher=False,
        )

    @override_settings(ADMISSION_OUTBOX_MAX_BACKLOG=1)
    @patch('core.admission.AdmissionController.consume_multi_tokens', return_value=TokenDecision(True))
    def test_render_backlog_cannot_block_agent_or_media(self, consume):
        self.operation()
        admit_expensive_operation(self.request, scope='interview.turn')
        admit_expensive_operation(self.request, scope='video-process')
        with self.assertRaises(CapacityRejected):
            admit_expensive_operation(self.request, scope='resume.preview')

    @patch('core.admission.AdmissionController.consume_multi_tokens', return_value=TokenDecision(True))
    def test_old_integration_event_does_not_block_commands(self, consume):
        IntegrationOutbox.objects.create(event_type='test.fixture', producer='core', aggregate_type='Fixture',
            aggregate_id='synthetic', payload={}, available_at=timezone.now() - timedelta(hours=1))
        admit_expensive_operation(self.request, scope='interview.turn')

    def test_published_unclaimed_is_recovered_once_then_bounded(self):
        operation = self.operation()
        for generation in range(4):
            latest = operation.dispatches.order_by('-fencing_token').first()
            OperationDispatchOutbox.objects.filter(pk=latest.pk).update(
                status='published', published_at=timezone.now() - timedelta(minutes=10))
            result = recover_stale_operations()
            if generation < 3:
                self.assertEqual(result['redispatched'], 1)
                self.assertEqual(recover_stale_operations()['redispatched'], 0)
            else:
                operation.refresh_from_db()
                self.assertEqual(operation.status, 'failed')
                self.assertEqual(operation.error_code, 'operation_unclaimed')

    def test_active_claim_is_not_redispatched(self):
        operation = self.operation()
        OperationDispatchOutbox.objects.filter(operation=operation).update(
            status='published', published_at=timezone.now() - timedelta(minutes=10))
        claim_operation(operation.pk, worker_id='synthetic-worker')
        self.assertEqual(recover_stale_operations()['redispatched'], 0)

    def test_expired_lease_cannot_continue_before_reconciler_runs(self):
        from core.operations import OperationExecutionContext, OperationLeaseLost
        operation = self.operation()
        claim = claim_operation(operation.pk, worker_id='fixture')
        type(operation).objects.filter(pk=operation.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(OperationLeaseLost):
            OperationExecutionContext(claim).raise_if_canceled()


class FFmpegDeadlineTests(SimpleTestCase):
    def test_silent_child_is_killed_on_stall(self):
        from video_uploads.services import FFmpegService
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.mp4'
            source.touch()
            service = FFmpegService()
            real_popen = __import__('subprocess').Popen
            children = []
            def spawn_child(cmd, **kw):
                process = real_popen(cmd[:1] + cmd[5:], **kw)
                children.append(process)
                return process
            with patch.object(service, 'get_duration', return_value=10), patch.object(
                service, 'build_transcode_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']
            ), patch('video_uploads.services.subprocess.Popen', wraps=__import__('subprocess').Popen) as spawn:
                # The service inserts FFmpeg-only switches. Strip those solely
                # for this synthetic Python child, keeping real process cleanup.
                spawn.side_effect = spawn_child
                success, message = service.transcode(str(source), str(Path(directory) / 'result.mp4'),
                    timeout_seconds=3, stall_timeout_seconds=0.3)
                self.assertFalse(success)
                self.assertEqual(message, '转码进度停滞')
                self.assertIsNotNone(children[0].poll())
