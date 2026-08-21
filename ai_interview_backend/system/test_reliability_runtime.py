from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from .observability import (
    build_runtime_capabilities,
    inspect_celery_workers,
    render_prometheus_metrics,
)


class CeleryTopologySettingsTests(SimpleTestCase):
    def test_only_queue_names_are_versioned(self):
        self.assertEqual(settings.CELERY_TOPOLOGY_VERSION, 'v2')
        self.assertTrue(all(name.startswith('ifaceoff.v2.') for name in settings.CELERY_MAIN_QUEUE_NAMES))
        self.assertEqual(settings.CELERY_COMMAND_EXCHANGE, 'ifaceoff.commands')
        self.assertEqual(settings.CELERY_EVENT_EXCHANGE, 'ifaceoff.events')
        self.assertEqual(settings.CELERY_DEAD_EXCHANGE, 'ifaceoff.dlx')
        self.assertFalse(any('.retry' in queue.name for queue in settings.CELERY_TASK_QUEUES))

    def test_every_main_queue_has_a_bounded_domain_dlq(self):
        self.assertEqual(len(settings.CELERY_MAIN_QUEUE_NAMES), len(settings.CELERY_DLQ_NAMES))
        queues = {queue.name: queue for queue in settings.CELERY_TASK_QUEUES}
        for main_name in settings.CELERY_MAIN_QUEUE_NAMES:
            queue = queues[main_name]
            dlq = queues[f'{main_name}.dlq']
            self.assertEqual(queue.queue_arguments['x-dead-letter-exchange'], 'ifaceoff.dlx')
            self.assertEqual(dlq.exchange.name, 'ifaceoff.dlx')
            self.assertEqual(dlq.queue_arguments['x-queue-type'], 'quorum')
            self.assertEqual(dlq.queue_arguments['x-overflow'], 'reject-publish')
            self.assertGreater(dlq.queue_arguments['x-max-length'], 0)
            self.assertGreater(dlq.queue_arguments['x-max-length-bytes'], 0)

    def test_critical_quorum_queues_reject_publish_when_full(self):
        queues = {queue.name: queue for queue in settings.CELERY_TASK_QUEUES}
        critical = (
            settings.CELERY_AGENT_QUEUE,
            settings.CELERY_CAREER_QUEUE,
            settings.CELERY_DOCUMENT_QUEUE,
            settings.CELERY_RESUME_RENDER_QUEUE,
            settings.CELERY_MEDIA_QUEUE,
            settings.CELERY_COMMUNITY_MODERATION_QUEUE,
            settings.CELERY_PUBLISHER_QUEUE,
        )
        for name in critical:
            arguments = queues[name].queue_arguments
            self.assertEqual(arguments['x-queue-type'], 'quorum')
            self.assertEqual(arguments['x-overflow'], 'reject-publish')
            self.assertGreater(arguments['x-max-length'], 0)
            self.assertGreater(arguments['x-max-length-bytes'], 0)

    def test_publisher_routes_precede_notification_wildcards(self):
        routes = settings.CELERY_TASK_ROUTES
        keys = list(routes)
        self.assertEqual(
            routes['notifications.tasks.publish_notification_outbox']['queue'],
            settings.CELERY_PUBLISHER_QUEUE,
        )
        self.assertEqual(
            routes['core.tasks.publish_integration_outbox']['queue'],
            settings.CELERY_PUBLISHER_QUEUE,
        )
        self.assertEqual(
            routes['interviews.tasks.recover_stale_agent_executions']['queue'],
            settings.CELERY_PUBLISHER_QUEUE,
        )
        self.assertEqual(
            routes['core.tasks.recover_stale_operations_task']['queue'],
            settings.CELERY_PUBLISHER_QUEUE,
        )
        self.assertLess(
            keys.index('notifications.tasks.publish_notification_outbox'),
            keys.index('notifications.tasks.*'),
        )
        self.assertNotEqual(settings.CELERY_PUBLISHER_QUEUE, settings.CELERY_NOTIFICATION_QUEUE)
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE['publish-operation-dispatch-outbox']['options']['queue'],
            settings.CELERY_PUBLISHER_QUEUE,
        )

    def test_delivery_and_worker_safety_contracts(self):
        self.assertFalse(settings.CELERY_TASK_CREATE_MISSING_QUEUES)
        self.assertTrue(settings.CELERY_BROKER_TRANSPORT_OPTIONS['confirm_publish'])
        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertTrue(settings.CELERY_TASK_REJECT_ON_WORKER_LOST)
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)
        self.assertLess(settings.CELERY_TASK_SOFT_TIME_LIMIT, settings.CELERY_TASK_TIME_LIMIT)
        self.assertGreater(settings.AGENT_EXECUTION_LEASE_SECONDS, 300)
        self.assertEqual(settings.CELERY_EVENTS_QUEUE, settings.CELERY_EVENT_QUEUE)

    def test_coordination_and_channels_are_bounded(self):
        self.assertEqual(settings.OPERATION_LEASE_SECONDS, 300)
        self.assertEqual(settings.OPERATION_DISPATCH_BATCH_SIZE, 100)
        self.assertEqual(
            settings.ASYNC_OPERATION_V2_DOMAINS,
            ('resume', 'career', 'knowledge', 'media', 'community'),
        )
        for alias in ('default', 'coordination', 'realtime'):
            options = settings.CACHES[alias]['OPTIONS']
            self.assertGreater(options['SOCKET_CONNECT_TIMEOUT'], 0)
            self.assertGreater(options['SOCKET_TIMEOUT'], 0)
            self.assertGreater(options['CONNECTION_POOL_KWARGS']['health_check_interval'], 0)
        channels = settings.CHANNEL_LAYERS['default']['CONFIG']
        self.assertGreater(channels['capacity'], 0)
        self.assertGreater(channels['expiry'], 0)
        self.assertIn('websocket.send!*', channels['channel_capacity'])


class DeclareCeleryTopologyCommandTests(SimpleTestCase):
    def test_declares_every_configured_queue(self):
        bound = Mock()
        fake_queue = Mock()
        fake_queue.return_value = bound
        channel = Mock()
        connection = Mock()
        connection.channel.return_value = channel
        fake_app = Mock()
        fake_app.connection_for_write.return_value = connection
        stdout = StringIO()

        with override_settings(
            CELERY_TASK_QUEUES=(fake_queue,),
            CELERY_MAIN_QUEUE_NAMES=('ifaceoff.v2.example',),
            CELERY_DLQ_NAMES=('ifaceoff.v2.example.dlq',),
            CELERY_TOPOLOGY_VERSION='v2',
        ), patch(
            'system.management.commands.declare_celery_topology.app',
            fake_app,
        ):
            call_command('declare_celery_topology', stdout=stdout)

        connection.ensure_connection.assert_called_once_with(max_retries=3)
        bound.declare.assert_called_once_with()
        channel.close.assert_called_once_with()
        connection.release.assert_called_once_with()
        self.assertIn('version=v2', stdout.getvalue())


class RuntimeObservabilityTests(SimpleTestCase):
    @patch('ai_interview_backend.celery_app.app')
    def test_worker_snapshot_reports_required_consumers_without_worker_names(self, app):
        inspector = app.control.inspect.return_value
        inspector.ping.return_value = {'celery@host-a': {'ok': 'pong'}}
        inspector.active_queues.return_value = {
            'celery@host-a': [
                {'name': settings.CELERY_DEFAULT_QUEUE},
                {'name': settings.CELERY_AGENT_QUEUE},
                {'name': settings.CELERY_PUBLISHER_QUEUE},
            ]
        }

        snapshot = inspect_celery_workers()

        self.assertEqual(snapshot['workers'], 1)
        self.assertTrue(snapshot['publisher_available'])
        self.assertTrue(snapshot['agent_worker_available'])
        self.assertEqual(snapshot['missing_required_queues'], [])
        self.assertNotIn('celery@host-a', str(snapshot))

    def test_capabilities_fail_closed_by_dependency(self):
        checks = {
            'database': {'ok': True},
            'agent_database': {'ok': True},
            'redis_coordination': {'ok': False},
            'redis_realtime': {'ok': False},
            'rabbitmq': {'ok': True},
            'celery_worker': {'ok': True},
        }
        capabilities = build_runtime_capabilities(
            checks,
            {'publisher_available': True, 'agent_worker_available': True},
        )
        self.assertTrue(capabilities['database_reads'])
        self.assertFalse(capabilities['expensive_operations'])
        self.assertFalse(capabilities['realtime'])
        self.assertTrue(capabilities['outbox_delivery'])

    def test_prometheus_output_has_only_bounded_labels(self):
        snapshot = {
            'integration_outbox': {
                'total': 3,
                'by_status': {'pending': 2, 'published': 1},
                'actionable': 2,
                'oldest_actionable_age_seconds': 9,
            },
        }
        output = render_prometheus_metrics(snapshot)
        self.assertIn('ifaceoff_build_info{celery_topology_version="v2"} 1', output)
        self.assertIn(
            'ifaceoff_async_records{kind="integration_outbox",status="pending"} 2',
            output,
        )
        self.assertNotIn('payload', output)
        self.assertNotIn('event_id', output)
        self.assertNotIn('user_id', output)

    @patch('system.views.operational_queue_snapshot')
    def test_internal_metrics_endpoint_degrades_to_error_gauge(self, snapshot):
        snapshot.side_effect = RuntimeError('database unavailable')
        response = self.client.get('/internal/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ifaceoff_metrics_collection_error 1', response.content)
        self.assertNotIn(b'database unavailable', response.content)


class ProductionComposeContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo_root = Path(settings.BASE_DIR).parent
        cls.base = (cls.repo_root / 'docker-compose.yml').read_text(encoding='utf-8')
        cls.production = (
            cls.repo_root / 'docker-compose.production-resilience.yml'
        ).read_text(encoding='utf-8')
        cls.infrastructure = (
            cls.repo_root / 'docker-compose.infra.yml'
        ).read_text(encoding='utf-8')

    def test_production_has_isolated_publish_and_long_task_workers(self):
        for service in (
            'celery-publisher-worker:',
            'celery-agent-worker:',
            'celery-document-worker:',
            'celery-media-worker:',
            'celery-resume-render-worker:',
            'celery-events-worker:',
        ):
            self.assertIn(service, self.production)
        self.assertIn('ifaceoff.${CELERY_TOPOLOGY_VERSION:-v2}.publisher', self.production)
        self.assertIn('ifaceoff.${CELERY_TOPOLOGY_VERSION:-v2}.notifications', self.production)
        self.assertIn('celery -A ai_interview_backend inspect ping', self.production)
        self.assertIn('CELERY_WORKER_ROLE:', self.production)
        self.assertIn('mem_limit:', self.production)
        self.assertIn('pids_limit:', self.production)

    def test_runtime_declares_topology_and_persists_rabbitmq(self):
        self.assertIn('celery-topology:', self.base)
        self.assertIn('declare_celery_topology', self.base)
        self.assertIn('rabbitmq_data:/var/lib/rabbitmq', self.base)
        self.assertIn('docker/rabbitmq/enabled_plugins', self.base)

    def test_three_redis_domains_have_explicit_memory_contracts(self):
        for compose in (self.production, self.infrastructure):
            self.assertIn('redis-cache:', compose)
            self.assertIn('redis-coordination:', compose)
            self.assertIn('redis-realtime:', compose)
            self.assertIn('allkeys-lfu', compose)
            self.assertGreaterEqual(compose.count('noeviction'), 2)
            self.assertGreaterEqual(compose.count('--maxmemory'), 3)
