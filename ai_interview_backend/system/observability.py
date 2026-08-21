"""Low-cardinality operational snapshots for readiness and Prometheus."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from django.conf import settings
from django.db.models import Count, Min
from django.utils import timezone


def _status_counts(model) -> dict[str, int]:
    configured = {value: 0 for value, _label in model.Status.choices}
    rows = model.objects.values('status').annotate(total=Count('pk'))
    for row in rows:
        configured[str(row['status'])] = int(row['total'])
    return configured


def _oldest_age_seconds(model, statuses: tuple[str, ...]) -> int:
    oldest: datetime | None = (
        model.objects.filter(status__in=statuses)
        .aggregate(oldest=Min('created_at'))
        .get('oldest')
    )
    if oldest is None:
        return 0
    return max(0, int((timezone.now() - oldest).total_seconds()))


def operational_queue_snapshot() -> dict[str, dict]:
    """Return bounded, aggregate-only state; never expose payloads or row IDs."""

    from core.models import (
        AsyncOperation,
        ConsumerInbox,
        IntegrationOutbox,
        OperationDispatchOutbox,
    )
    from interviews.models import InterviewAgentDispatch

    definitions = (
        (
            'operations',
            AsyncOperation,
            (
                AsyncOperation.Status.PENDING,
                AsyncOperation.Status.CLAIMED,
                AsyncOperation.Status.RUNNING,
                AsyncOperation.Status.RETRYING,
                AsyncOperation.Status.CANCEL_REQUESTED,
            ),
        ),
        (
            'operation_dispatch',
            OperationDispatchOutbox,
            (
                OperationDispatchOutbox.Status.PENDING,
                OperationDispatchOutbox.Status.PUBLISHING,
                OperationDispatchOutbox.Status.FAILED,
            ),
        ),
        (
            'integration_outbox',
            IntegrationOutbox,
            (
                IntegrationOutbox.Status.PENDING,
                IntegrationOutbox.Status.PUBLISHING,
                IntegrationOutbox.Status.FAILED,
            ),
        ),
        (
            'consumer_inbox',
            ConsumerInbox,
            (ConsumerInbox.Status.PROCESSING, ConsumerInbox.Status.FAILED),
        ),
        (
            'agent_dispatch',
            InterviewAgentDispatch,
            (InterviewAgentDispatch.Status.PENDING, InterviewAgentDispatch.Status.FAILED),
        ),
    )

    snapshot = {}
    for name, model, actionable_statuses in definitions:
        by_status = _status_counts(model)
        snapshot[name] = {
            'total': sum(by_status.values()),
            'by_status': by_status,
            'actionable': sum(by_status.get(status, 0) for status in actionable_statuses),
            'oldest_actionable_age_seconds': _oldest_age_seconds(model, actionable_statuses),
        }
    return snapshot


def inspect_celery_workers() -> dict:
    """Inspect consumers without returning unstable worker hostnames."""

    from ai_interview_backend.celery_app import app

    timeout = float(getattr(settings, 'CELERY_INSPECT_TIMEOUT_SECONDS', 2))
    inspector = app.control.inspect(timeout=timeout)
    ping_replies = inspector.ping() or {}
    if not ping_replies:
        raise RuntimeError('no_worker_heartbeat')

    active_replies = inspector.active_queues() or {}
    consumers = Counter()
    for worker_queues in active_replies.values():
        for queue in worker_queues or ():
            name = str(queue.get('name') or '')
            if name in settings.CELERY_MAIN_QUEUE_NAMES:
                consumers[name] += 1

    required = (
        settings.CELERY_DEFAULT_QUEUE,
        settings.CELERY_AGENT_QUEUE,
        settings.CELERY_PUBLISHER_QUEUE,
    )
    return {
        'workers': len(ping_replies),
        'queue_consumers': {
            name: int(consumers.get(name, 0))
            for name in settings.CELERY_MAIN_QUEUE_NAMES
        },
        'missing_required_queues': [name for name in required if not consumers.get(name)],
        'publisher_available': bool(consumers.get(settings.CELERY_PUBLISHER_QUEUE)),
        'agent_worker_available': bool(consumers.get(settings.CELERY_AGENT_QUEUE)),
    }


def build_runtime_capabilities(checks: dict, worker_state: dict | None = None) -> dict[str, bool]:
    worker_state = worker_state or {}

    def healthy(name):
        return bool(checks.get(name, {}).get('ok'))

    database = healthy('database')
    broker = healthy('rabbitmq')
    workers = healthy('celery_worker')
    coordination = healthy('redis_coordination')
    realtime = healthy('redis_realtime')
    agent_database = healthy('agent_database')
    return {
        'database_reads': database,
        'database_writes': database,
        'cache_reads': database,
        'realtime': database and realtime,
        'expensive_operations': database and coordination,
        'broker_publish': broker,
        'async_jobs': database and broker and workers,
        'outbox_delivery': (
            database
            and broker
            and workers
            and bool(worker_state.get('publisher_available'))
        ),
        'agent_execution': (
            database
            and broker
            and workers
            and agent_database
            and bool(worker_state.get('agent_worker_available'))
        ),
    }


def _escape_label(value) -> str:
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


def render_prometheus_metrics(snapshot: dict | None, *, collection_error=False) -> str:
    """Render Prometheus text without high-cardinality IDs, users or error strings."""

    lines = [
        '# HELP ifaceoff_build_info Static runtime topology metadata.',
        '# TYPE ifaceoff_build_info gauge',
        'ifaceoff_build_info{celery_topology_version="%s"} 1'
        % _escape_label(settings.CELERY_TOPOLOGY_VERSION),
        '# HELP ifaceoff_metrics_collection_error Whether database aggregation failed.',
        '# TYPE ifaceoff_metrics_collection_error gauge',
        f'ifaceoff_metrics_collection_error {1 if collection_error else 0}',
        '# HELP ifaceoff_celery_queue_configured Declared main Celery queues.',
        '# TYPE ifaceoff_celery_queue_configured gauge',
    ]
    lines.extend(
        f'ifaceoff_celery_queue_configured{{queue="{_escape_label(queue)}"}} 1'
        for queue in settings.CELERY_MAIN_QUEUE_NAMES
    )

    if snapshot:
        lines.extend((
            '# HELP ifaceoff_async_records Current durable async records by kind and status.',
            '# TYPE ifaceoff_async_records gauge',
        ))
        for kind in sorted(snapshot):
            state = snapshot[kind]
            for status, total in sorted(state['by_status'].items()):
                lines.append(
                    'ifaceoff_async_records{kind="%s",status="%s"} %d'
                    % (_escape_label(kind), _escape_label(status), int(total))
                )
        lines.extend((
            '# HELP ifaceoff_async_actionable Current records requiring delivery or processing.',
            '# TYPE ifaceoff_async_actionable gauge',
            '# HELP ifaceoff_async_oldest_actionable_age_seconds Age of the oldest actionable record.',
            '# TYPE ifaceoff_async_oldest_actionable_age_seconds gauge',
        ))
        for kind in sorted(snapshot):
            state = snapshot[kind]
            escaped_kind = _escape_label(kind)
            lines.append(
                f'ifaceoff_async_actionable{{kind="{escaped_kind}"}} {int(state["actionable"])}'
            )
            lines.append(
                'ifaceoff_async_oldest_actionable_age_seconds'
                f'{{kind="{escaped_kind}"}} {int(state["oldest_actionable_age_seconds"])}'
            )

    return '\n'.join(lines) + '\n'
