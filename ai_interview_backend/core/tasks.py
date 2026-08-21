from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .events import consume_event, event_envelope, retry_delay
from .models import AsyncOperation, IntegrationOutbox, OperationDispatchOutbox


@shared_task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def consume_integration_event(self, envelope):
    from .events import ConsumerInboxLeaseActive

    try:
        return consume_event(envelope)
    except ConsumerInboxLeaseActive as exc:
        raise self.retry(
            exc=exc,
            countdown=max(1, (exc.retry_after_ms + 999) // 1000),
        )


@shared_task(bind=True)
def publish_integration_outbox(self, batch_size=100):
    """Publish database events only after RabbitMQ confirms task acceptance."""

    now = timezone.now()
    stale_before = now - timedelta(minutes=5)
    max_attempts = int(getattr(settings, 'INTEGRATION_OUTBOX_MAX_ATTEMPTS', 12))
    with transaction.atomic():
        events = list(
            IntegrationOutbox.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status__in=[IntegrationOutbox.Status.PENDING, IntegrationOutbox.Status.FAILED])
                | Q(status=IntegrationOutbox.Status.PUBLISHING, locked_at__lt=stale_before),
                available_at__lte=now,
            )
            .order_by('created_at')[: max(1, min(int(batch_size), 500))]
        )
        for event in events:
            event.status = IntegrationOutbox.Status.PUBLISHING
            event.locked_at = now
            event.attempts += 1
            event.save(update_fields=['status', 'locked_at', 'attempts', 'updated_at'])

    published = 0
    failed = 0
    for event in events:
        try:
            consume_integration_event.apply_async(
                args=[event_envelope(event)],
                queue=settings.CELERY_EVENTS_QUEUE,
                exchange=settings.CELERY_EVENTS_EXCHANGE,
                routing_key=event.event_type,
                mandatory=True,
                retry=True,
                retry_policy={
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.5,
                    'interval_max': 2,
                },
            )
            IntegrationOutbox.objects.filter(pk=event.pk).update(
                status=IntegrationOutbox.Status.PUBLISHED,
                published_at=timezone.now(),
                locked_at=None,
                last_error='',
            )
            published += 1
        except Exception as exc:
            terminal = event.attempts >= max_attempts
            IntegrationOutbox.objects.filter(pk=event.pk).update(
                status=IntegrationOutbox.Status.DEAD if terminal else IntegrationOutbox.Status.FAILED,
                available_at=timezone.now() + retry_delay(event.attempts),
                locked_at=None,
                last_error=f'{type(exc).__name__}: {exc}'[:2000],
            )
            failed += 1
    return {'claimed': len(events), 'published': published, 'failed': failed}


@shared_task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=840,
    time_limit=900,
)
def execute_operation(self, operation_id: str):
    """Claim and execute a registered operation using PostgreSQL fencing."""

    from .operation_registry import get_operation_handler
    from .operations import (
        OperationCanceled,
        OperationExecutionContext,
        OperationLeaseLost,
        RetryableOperationError,
        TerminalOperationError,
        claim_operation,
        complete_operation,
        fail_operation,
        normalize_handler_result,
        start_operation,
    )

    worker_id = f'{getattr(self.request, "hostname", "worker")}:{self.request.id or "unknown"}'
    claim = claim_operation(operation_id, worker_id=worker_id)
    if claim is None:
        operation = AsyncOperation.objects.filter(pk=operation_id).values('status', 'result_type', 'result_id').first()
        return {'operation_id': str(operation_id), 'idempotent_replay': True, **(operation or {'status': 'missing'})}

    context = OperationExecutionContext(claim)
    start_operation(claim)
    try:
        handler = get_operation_handler(context.get_operation().operation_type)
        result = normalize_handler_result(handler(context))
        context.raise_if_canceled()
        operation = complete_operation(
            claim,
            result_type=result.result_type,
            result_id=result.result_id,
            result=result.result,
            metadata=result.metadata,
        )
        return {'operation_id': str(operation.id), 'status': operation.status, 'result_id': operation.result_id}
    except (OperationCanceled, OperationLeaseLost) as exc:
        operation = AsyncOperation.objects.filter(pk=operation_id).values('status').first()
        return {
            'operation_id': str(operation_id),
            'status': (operation or {}).get('status', 'missing'),
            'fenced': isinstance(exc, OperationLeaseLost),
        }
    except RetryableOperationError as exc:
        try:
            operation = fail_operation(
                claim,
                error_code=exc.code,
                error_message=str(exc),
                retryable=True,
                retry_after_seconds=exc.retry_after_seconds,
            )
            return {'operation_id': str(operation.id), 'status': operation.status, 'error_code': operation.error_code}
        except (OperationCanceled, OperationLeaseLost):
            return {'operation_id': str(operation_id), 'fenced': True}
    except TerminalOperationError as exc:
        try:
            operation = fail_operation(
                claim,
                error_code=exc.code,
                error_message=str(exc),
                retryable=False,
            )
            return {'operation_id': str(operation.id), 'status': operation.status, 'error_code': operation.error_code}
        except (OperationCanceled, OperationLeaseLost):
            return {'operation_id': str(operation_id), 'fenced': True}
    except (ConnectionError, TimeoutError) as exc:
        try:
            operation = fail_operation(
                claim,
                error_code=type(exc).__name__,
                error_message=str(exc),
                retryable=True,
            )
            return {'operation_id': str(operation.id), 'status': operation.status, 'error_code': operation.error_code}
        except (OperationCanceled, OperationLeaseLost):
            return {'operation_id': str(operation_id), 'fenced': True}
    except Exception as exc:
        try:
            operation = fail_operation(
                claim,
                error_code=type(exc).__name__,
                error_message=str(exc),
                retryable=False,
            )
            return {'operation_id': str(operation.id), 'status': operation.status, 'error_code': operation.error_code}
        except (OperationCanceled, OperationLeaseLost):
            return {'operation_id': str(operation_id), 'fenced': True}


@shared_task(bind=True, acks_late=True, soft_time_limit=30, time_limit=45)
def publish_operation_dispatch_outbox(self, batch_size=100):
    """Publish durable operation commands; RabbitMQ carries only operation IDs."""

    now = timezone.now()
    stale_before = now - timedelta(minutes=5)
    dispatch_ids = list(
        OperationDispatchOutbox.objects.filter(
            Q(status__in=[OperationDispatchOutbox.Status.PENDING, OperationDispatchOutbox.Status.FAILED])
            | Q(status=OperationDispatchOutbox.Status.PUBLISHING, locked_at__lt=stale_before),
            available_at__lte=now,
        ).order_by('created_at').values_list('id', flat=True)[: max(1, min(int(batch_size), 500))]
    )
    published = 0
    failed = 0
    dead_operation_ids = []
    for dispatch_id in dispatch_ids:
        with transaction.atomic():
            dispatch = OperationDispatchOutbox.objects.select_for_update(skip_locked=True).select_related(
                'operation',
            ).filter(pk=dispatch_id).first()
            if not dispatch or dispatch.status not in {
                OperationDispatchOutbox.Status.PENDING,
                OperationDispatchOutbox.Status.FAILED,
                OperationDispatchOutbox.Status.PUBLISHING,
            }:
                continue
            if (
                dispatch.status == OperationDispatchOutbox.Status.PUBLISHING
                and dispatch.locked_at
                and dispatch.locked_at >= stale_before
            ):
                continue
            if dispatch.operation.status in {
                AsyncOperation.Status.SUCCEEDED,
                AsyncOperation.Status.FAILED,
                AsyncOperation.Status.CANCELED,
            }:
                dispatch.status = OperationDispatchOutbox.Status.CANCELED
                dispatch.locked_at = None
                dispatch.version += 1
                dispatch.save(update_fields=['status', 'locked_at', 'version', 'updated_at'])
                continue
            dispatch.status = OperationDispatchOutbox.Status.PUBLISHING
            dispatch.locked_at = now
            dispatch.attempts += 1
            dispatch.version += 1
            dispatch.save(update_fields=['status', 'locked_at', 'attempts', 'version', 'updated_at'])

        try:
            result = execute_operation.apply_async(
                args=[str(dispatch.operation_id)],
                queue=dispatch.queue,
                routing_key=dispatch.routing_key or settings.CELERY_TASK_DEFAULT_ROUTING_KEY,
                mandatory=True,
                retry=True,
                retry_policy={
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.5,
                    'interval_max': 2,
                },
            )
            updated = OperationDispatchOutbox.objects.filter(
                pk=dispatch.pk,
                status=OperationDispatchOutbox.Status.PUBLISHING,
                version=dispatch.version,
            ).update(
                status=OperationDispatchOutbox.Status.PUBLISHED,
                celery_task_id=result.id or '',
                published_at=timezone.now(),
                locked_at=None,
                last_error='',
                version=dispatch.version + 1,
                updated_at=timezone.now(),
            )
            if updated:
                AsyncOperation.objects.filter(pk=dispatch.operation_id).exclude(
                    status__in=[
                        AsyncOperation.Status.SUCCEEDED,
                        AsyncOperation.Status.FAILED,
                        AsyncOperation.Status.CANCELED,
                    ],
                ).update(celery_task_id=result.id or '', updated_at=timezone.now())
                published += 1
        except Exception as exc:
            terminal = dispatch.attempts >= dispatch.max_attempts
            updated = OperationDispatchOutbox.objects.filter(
                pk=dispatch.pk,
                status=OperationDispatchOutbox.Status.PUBLISHING,
                version=dispatch.version,
            ).update(
                status=OperationDispatchOutbox.Status.DEAD if terminal else OperationDispatchOutbox.Status.FAILED,
                available_at=timezone.now() + retry_delay(dispatch.attempts),
                locked_at=None,
                last_error=f'{type(exc).__name__}: {exc}'[:2000],
                version=dispatch.version + 1,
                updated_at=timezone.now(),
            )
            if updated and terminal:
                dead_operation_ids.append((dispatch.operation_id, str(exc)))
            failed += int(bool(updated))

    if dead_operation_ids:
        from .operations import mark_dispatch_dead
        for operation_id, error in dead_operation_ids:
            mark_dispatch_dead(operation_id, error_message=error)
    return {'claimed': len(dispatch_ids), 'published': published, 'failed': failed, 'dead': len(dead_operation_ids)}


@shared_task(acks_late=True)
def recover_stale_operations_task(batch_size=200):
    from .operations import recover_stale_operations

    result = recover_stale_operations(batch_size=batch_size)
    if result['recovered']:
        publish_operation_dispatch_outbox.apply_async(
            queue=settings.CELERY_PUBLISHER_QUEUE,
        )
    return result
