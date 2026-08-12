from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from .models import AsyncOperation, OperationDispatchOutbox, OperationEvent
from .operation_registry import OperationHandlerResult


TERMINAL_STATUSES = frozenset({
    AsyncOperation.Status.SUCCEEDED,
    AsyncOperation.Status.FAILED,
    AsyncOperation.Status.CANCELED,
})
ACTIVE_STATUSES = frozenset({
    AsyncOperation.Status.CLAIMED,
    AsyncOperation.Status.RUNNING,
})
RUNNABLE_STATUSES = frozenset({
    AsyncOperation.Status.PENDING,
    AsyncOperation.Status.RETRYING,
})

_FORBIDDEN_EVENT_KEYS = {
    'answer', 'answer_text', 'api_key', 'document_content', 'password',
    'prompt', 'resume', 'resume_content', 'secret', 'token',
}
_SAFE_TECHNICAL_TOKEN_KEYS = {
    'fencing_token', 'input_tokens', 'output_tokens', 'token_count', 'total_tokens',
}


class OperationConflict(RuntimeError):
    pass


class OperationLeaseLost(OperationConflict):
    pass


class OperationCanceled(OperationConflict):
    pass


class RetryableOperationError(RuntimeError):
    def __init__(self, code: str, message: str = '', *, retry_after_seconds: float = 5):
        self.code = str(code or 'operation_retryable_error')[:120]
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))
        super().__init__(message or self.code)


class TerminalOperationError(RuntimeError):
    def __init__(self, code: str, message: str = ''):
        self.code = str(code or 'operation_terminal_error')[:120]
        super().__init__(message or self.code)


@dataclass(frozen=True)
class OperationClaim:
    operation_id: uuid.UUID
    worker_id: str
    fencing_token: int
    lease_expires_at: Any


@dataclass(frozen=True)
class OperationExecutionContext:
    claim: OperationClaim

    @property
    def operation_id(self):
        return self.claim.operation_id

    def get_operation(self) -> AsyncOperation:
        return AsyncOperation.objects.get(pk=self.claim.operation_id)

    def heartbeat(self, *, lease_seconds: int | None = None) -> bool:
        return heartbeat_operation(self.claim, lease_seconds=lease_seconds)

    def checkpoint(
        self,
        progress: int,
        *,
        event_type: str = 'operation.progress',
        payload: dict[str, Any] | None = None,
        lease_seconds: int | None = None,
    ) -> AsyncOperation:
        return checkpoint_operation(
            self.claim,
            progress=progress,
            event_type=event_type,
            payload=payload,
            lease_seconds=lease_seconds,
        )

    def raise_if_canceled(self) -> None:
        current = AsyncOperation.objects.filter(pk=self.claim.operation_id).values(
            'status', 'fencing_token',
        ).first()
        if not current or current['status'] in {
            AsyncOperation.Status.CANCEL_REQUESTED,
            AsyncOperation.Status.CANCELED,
        }:
            raise OperationCanceled('operation_canceled')
        if int(current['fencing_token']) != self.claim.fencing_token:
            raise OperationLeaseLost('operation_fenced')


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _walk_safe_payload(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError('operation_event_payload_too_deep')
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            forbidden_suffix = key.endswith(('_password', '_secret', '_api_key')) or (
                key.endswith('_token') and key not in _SAFE_TECHNICAL_TOKEN_KEYS
            )
            if key in _FORBIDDEN_EVENT_KEYS or forbidden_suffix:
                raise ValueError('operation_event_contains_sensitive_field')
            _walk_safe_payload(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 100:
            raise ValueError('operation_event_payload_too_many_items')
        for item in value:
            _walk_safe_payload(item, depth=depth + 1)


def safe_operation_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    value = _json_safe(payload or {})
    if not isinstance(value, dict):
        raise ValueError('operation_event_payload_must_be_object')
    _walk_safe_payload(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) > 16 * 1024:
        raise ValueError('operation_event_payload_too_large')
    return value


def _sanitize_result_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        raise ValueError('operation_result_too_deep')
    if isinstance(value, dict):
        result = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized_key = key.strip().lower()
            forbidden_suffix = normalized_key.endswith(('_password', '_secret', '_api_key')) or (
                normalized_key.endswith('_token')
                and normalized_key not in _SAFE_TECHNICAL_TOKEN_KEYS
            )
            if normalized_key in _FORBIDDEN_EVENT_KEYS or forbidden_suffix:
                continue
            result[key] = _sanitize_result_value(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_sanitize_result_value(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    return value


def safe_operation_result(result: dict[str, Any] | None) -> dict[str, Any]:
    value = _json_safe(result or {})
    if not isinstance(value, dict):
        raise ValueError('operation_result_must_be_object')
    value = _sanitize_result_value(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) > 16 * 1024:
        raise ValueError('operation_result_too_large')
    return value


def _append_event_locked(
    operation: AsyncOperation,
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
) -> OperationEvent:
    operation.last_event_sequence += 1
    operation.save(update_fields=['last_event_sequence', 'updated_at'])
    return OperationEvent.objects.create(
        operation=operation,
        sequence=operation.last_event_sequence,
        event_type=str(event_type or '')[:120],
        status=operation.status,
        payload=safe_operation_payload(payload),
    )


@transaction.atomic
def append_operation_event(
    operation_id,
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
) -> OperationEvent:
    operation = AsyncOperation.objects.select_for_update().get(pk=operation_id)
    return _append_event_locked(operation, event_type, payload=payload)


@transaction.atomic
def create_operation(
    *,
    user,
    operation_type: str,
    source_app: str,
    source_model: str,
    source_id: str,
    title: str,
    input_type: str = '',
    input_id: str = '',
    input_version: str = '',
    input_hash: str = '',
    idempotency_key_hash: str = '',
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 5,
    correlation_id=None,
    trace_id: str = '',
) -> AsyncOperation:
    if not correlation_id or not trace_id:
        from .middleware import get_current_correlation_id, get_current_trace_id

        correlation_id = correlation_id or get_current_correlation_id() or None
        trace_id = trace_id or get_current_trace_id()
    operation = AsyncOperation.objects.create(
        user=user,
        operation_type=str(operation_type)[:80],
        source_app=str(source_app)[:40],
        source_model=str(source_model)[:80],
        source_id=str(source_id)[:80],
        title=str(title)[:255],
        input_type=str(input_type)[:80],
        input_id=str(input_id)[:120],
        input_version=str(input_version)[:120],
        input_hash=str(input_hash)[:64],
        idempotency_key_hash=str(idempotency_key_hash or '')[:64],
        metadata=safe_operation_payload(metadata),
        max_attempts=max(1, min(int(max_attempts), 100)),
        correlation_id=uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4(),
        trace_id=str(trace_id or '')[:64],
    )
    _append_event_locked(operation, 'operation.accepted', payload={
        'operation_type': operation.operation_type,
        'input_id': operation.input_id or None,
    })
    # A run_idempotent callback exposes its current claim through a context
    # variable. Binding here makes the public header/body operation identity
    # converge before the callback returns.
    from .idempotency import bind_current_operation
    bind_current_operation(operation)
    return operation


def routing_key_for_queue(queue_name: str) -> str:
    for configured_queue in getattr(settings, 'CELERY_TASK_QUEUES', ()):
        if getattr(configured_queue, 'name', None) == queue_name:
            return str(
                getattr(configured_queue, 'routing_key', '')
                or settings.CELERY_TASK_DEFAULT_ROUTING_KEY
            )[:120]
    return str(settings.CELERY_TASK_DEFAULT_ROUTING_KEY)[:120]


@transaction.atomic
def create_operation_with_dispatch(
    *,
    queue: str | None = None,
    routing_key: str = '',
    dispatch_max_attempts: int = 12,
    kick_publisher: bool = True,
    **operation_kwargs,
) -> AsyncOperation:
    operation = create_operation(**operation_kwargs)
    dispatch_queue = str(queue or settings.CELERY_DEFAULT_QUEUE)[:80]
    OperationDispatchOutbox.objects.create(
        operation=operation,
        queue=dispatch_queue,
        routing_key=str(routing_key or routing_key_for_queue(dispatch_queue))[:120],
        payload={'operation_id': str(operation.id)},
        fencing_token=0,
        max_attempts=max(1, min(int(dispatch_max_attempts), 100)),
        available_at=timezone.now(),
    )
    if kick_publisher:
        _kick_dispatch_publisher_on_commit()
    return operation


def _lease_seconds(value: int | None = None) -> int:
    configured = value if value is not None else getattr(settings, 'OPERATION_LEASE_SECONDS', 300)
    return max(15, min(int(configured), 3600))


@transaction.atomic
def claim_operation(operation_id, *, worker_id: str, lease_seconds: int | None = None) -> OperationClaim | None:
    now = timezone.now()
    operation = AsyncOperation.objects.select_for_update().filter(pk=operation_id).first()
    if not operation or operation.status in TERMINAL_STATUSES:
        return None
    if operation.status == AsyncOperation.Status.CANCEL_REQUESTED:
        operation.status = AsyncOperation.Status.CANCELED
        operation.completed_at = now
        operation.version += 1
        operation.save(update_fields=['status', 'completed_at', 'version', 'updated_at'])
        _append_event_locked(operation, 'operation.canceled')
        return None
    if operation.next_attempt_at and operation.next_attempt_at > now:
        return None
    lease_active = operation.lease_expires_at and operation.lease_expires_at > now
    if operation.status in ACTIVE_STATUSES and lease_active:
        return None
    if operation.status not in RUNNABLE_STATUSES and operation.status not in ACTIVE_STATUSES:
        return None
    if operation.attempt_count >= operation.max_attempts:
        operation.status = AsyncOperation.Status.FAILED
        operation.error_code = 'operation_attempts_exhausted'
        operation.error_message = 'Operation attempt limit exhausted before claim.'
        operation.retryable = False
        operation.completed_at = now
        operation.lease_owner = ''
        operation.lease_expires_at = None
        operation.fencing_token += 1
        operation.version += 1
        operation.save(update_fields=[
            'status', 'error_code', 'error_message', 'retryable', 'completed_at',
            'lease_owner', 'lease_expires_at', 'fencing_token', 'version', 'updated_at',
        ])
        _append_event_locked(operation, 'operation.failed', payload={
            'error_code': operation.error_code,
        })
        return None

    expires_at = now + timedelta(seconds=_lease_seconds(lease_seconds))
    operation.status = AsyncOperation.Status.CLAIMED
    operation.attempt_count += 1
    operation.lease_owner = str(worker_id or '')[:160]
    operation.lease_expires_at = expires_at
    operation.heartbeat_at = now
    operation.fencing_token += 1
    operation.version += 1
    operation.next_attempt_at = None
    operation.error_code = ''
    operation.error_message = ''
    operation.retryable = False
    if not operation.started_at:
        operation.started_at = now
    operation.save(update_fields=[
        'status', 'attempt_count', 'lease_owner', 'lease_expires_at', 'heartbeat_at',
        'fencing_token', 'version', 'next_attempt_at', 'error_code', 'error_message',
        'retryable', 'started_at', 'updated_at',
    ])
    _append_event_locked(operation, 'operation.claimed', payload={
        'attempt': operation.attempt_count,
        'fencing_token': operation.fencing_token,
    })
    return OperationClaim(operation.id, operation.lease_owner, operation.fencing_token, expires_at)


def _assert_claim_locked(operation: AsyncOperation, claim: OperationClaim, *, allow_claimed=True) -> None:
    statuses = {AsyncOperation.Status.RUNNING}
    if allow_claimed:
        statuses.add(AsyncOperation.Status.CLAIMED)
    if (
        operation.lease_owner != claim.worker_id
        or operation.fencing_token != claim.fencing_token
        or not operation.lease_expires_at
        or operation.lease_expires_at <= timezone.now()
    ):
        raise OperationLeaseLost('operation_lease_lost')
    if operation.status in {AsyncOperation.Status.CANCEL_REQUESTED, AsyncOperation.Status.CANCELED}:
        raise OperationCanceled('operation_canceled')
    if operation.status not in statuses:
        raise OperationLeaseLost('operation_lease_lost')


@transaction.atomic
def start_operation(claim: OperationClaim) -> AsyncOperation:
    operation = AsyncOperation.objects.select_for_update().get(pk=claim.operation_id)
    _assert_claim_locked(operation, claim)
    if operation.status == AsyncOperation.Status.RUNNING:
        return operation
    operation.status = AsyncOperation.Status.RUNNING
    operation.version += 1
    operation.save(update_fields=['status', 'version', 'updated_at'])
    _append_event_locked(operation, 'operation.running', payload={'attempt': operation.attempt_count})
    return operation


def heartbeat_operation(claim: OperationClaim, *, lease_seconds: int | None = None) -> bool:
    now = timezone.now()
    return AsyncOperation.objects.filter(
        pk=claim.operation_id,
        status__in=ACTIVE_STATUSES,
        lease_owner=claim.worker_id,
        fencing_token=claim.fencing_token,
        lease_expires_at__gt=now,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=_lease_seconds(lease_seconds)),
        version=F('version') + 1,
        updated_at=now,
    ) == 1


@transaction.atomic
def checkpoint_operation(
    claim: OperationClaim,
    *,
    progress: int,
    event_type: str = 'operation.progress',
    payload: dict[str, Any] | None = None,
    lease_seconds: int | None = None,
) -> AsyncOperation:
    operation = AsyncOperation.objects.select_for_update().get(pk=claim.operation_id)
    _assert_claim_locked(operation, claim)
    normalized_progress = max(operation.progress, min(max(int(progress), 0), 99))
    now = timezone.now()
    operation.progress = normalized_progress
    operation.heartbeat_at = now
    operation.lease_expires_at = now + timedelta(seconds=_lease_seconds(lease_seconds))
    operation.version += 1
    operation.save(update_fields=[
        'progress', 'heartbeat_at', 'lease_expires_at', 'version', 'updated_at',
    ])
    event_payload = safe_operation_payload(payload)
    event_payload['progress'] = normalized_progress
    _append_event_locked(operation, event_type, payload=event_payload)
    return operation


@transaction.atomic
def complete_operation(
    claim: OperationClaim,
    *,
    result_type: str = '',
    result_id: str = '',
    result: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncOperation:
    operation = AsyncOperation.objects.select_for_update().get(pk=claim.operation_id)
    _assert_claim_locked(operation, claim)
    safe_result = safe_operation_result(result)
    operation.status = AsyncOperation.Status.SUCCEEDED
    operation.progress = 100
    operation.result_type = str(result_type or '')[:80]
    operation.result_id = str(result_id or '')[:120]
    operation.result_json = safe_result
    operation.metadata = {
        **safe_operation_payload(operation.metadata),
        **safe_operation_payload(metadata),
    }
    operation.completed_at = timezone.now()
    operation.retryable = False
    operation.lease_owner = ''
    operation.lease_expires_at = None
    operation.version += 1
    operation.save(update_fields=[
        'status', 'progress', 'result_type', 'result_id', 'result_json', 'metadata',
        'completed_at', 'retryable', 'lease_owner', 'lease_expires_at', 'version', 'updated_at',
    ])
    _append_event_locked(operation, 'operation.succeeded', payload={
        'result_type': operation.result_type or None,
        'result_id': operation.result_id or None,
    })
    return operation


def _kick_dispatch_publisher_on_commit() -> None:
    publisher_queue = settings.CELERY_PUBLISHER_QUEUE

    def kick():
        try:
            from .tasks import publish_operation_dispatch_outbox
            publish_operation_dispatch_outbox.apply_async(queue=publisher_queue)
        except Exception:
            # PostgreSQL remains authoritative. A periodic publisher/recovery
            # pass can deliver the durable row after a broker outage.
            pass

    transaction.on_commit(kick)


def _create_dispatch_generation_locked(operation: AsyncOperation, *, available_at) -> OperationDispatchOutbox:
    """Append a dispatch generation; historical attempts are never rewritten."""

    latest = operation.dispatches.order_by('-fencing_token').first()
    next_fence = int(
        operation.dispatches.aggregate(value=Max('fencing_token')).get('value') or 0
    ) + (1 if latest is not None else 0)
    dispatch = OperationDispatchOutbox.objects.create(
        operation=operation,
        task_name='core.tasks.execute_operation',
        queue=latest.queue if latest else settings.CELERY_DEFAULT_QUEUE,
        routing_key=latest.routing_key if latest else settings.CELERY_TASK_DEFAULT_ROUTING_KEY,
        payload={'operation_id': str(operation.id)},
        max_attempts=latest.max_attempts if latest else 12,
        available_at=available_at,
        fencing_token=next_fence,
    )
    _kick_dispatch_publisher_on_commit()
    return dispatch


@transaction.atomic
def fail_operation(
    claim: OperationClaim,
    *,
    error_code: str,
    error_message: str = '',
    retryable: bool = False,
    retry_after_seconds: float = 5,
    dispatch_retry: bool = True,
) -> AsyncOperation:
    operation = AsyncOperation.objects.select_for_update().get(pk=claim.operation_id)
    _assert_claim_locked(operation, claim)
    should_retry = bool(retryable and operation.attempt_count < operation.max_attempts)
    now = timezone.now()
    operation.status = AsyncOperation.Status.RETRYING if should_retry else AsyncOperation.Status.FAILED
    operation.error_code = str(error_code or 'operation_failed')[:120]
    operation.error_message = str(error_message or '')[:2000]
    operation.retryable = should_retry
    operation.next_attempt_at = (
        now + timedelta(seconds=max(0.0, float(retry_after_seconds))) if should_retry else None
    )
    operation.completed_at = None if should_retry else now
    operation.lease_owner = ''
    operation.lease_expires_at = None
    operation.version += 1
    operation.save(update_fields=[
        'status', 'error_code', 'error_message', 'retryable', 'next_attempt_at',
        'completed_at', 'lease_owner', 'lease_expires_at', 'version', 'updated_at',
    ])
    if should_retry and dispatch_retry:
        _create_dispatch_generation_locked(operation, available_at=operation.next_attempt_at)
    _append_event_locked(
        operation,
        'operation.retrying' if should_retry else 'operation.failed',
        payload={'error_code': operation.error_code, 'attempt': operation.attempt_count},
    )
    return operation


@transaction.atomic
def request_operation_retry(
    operation_id,
    *,
    user=None,
    dispatch_retry: bool = True,
) -> AsyncOperation:
    queryset = AsyncOperation.objects.select_for_update().filter(pk=operation_id)
    if user is not None:
        queryset = queryset.filter(user=user)
    operation = queryset.get()
    if operation.status == AsyncOperation.Status.RETRYING:
        return operation
    if operation.status != AsyncOperation.Status.FAILED:
        raise OperationConflict(f'operation_not_retryable:{operation.status}')
    operation.status = AsyncOperation.Status.PENDING
    operation.retryable = False
    operation.error_code = ''
    operation.error_message = ''
    operation.completed_at = None
    operation.next_attempt_at = timezone.now()
    operation.max_attempts = max(operation.max_attempts, operation.attempt_count + 1)
    operation.version += 1
    operation.save(update_fields=[
        'status', 'retryable', 'error_code', 'error_message', 'completed_at',
        'next_attempt_at', 'max_attempts', 'version', 'updated_at',
    ])
    if dispatch_retry:
        _create_dispatch_generation_locked(operation, available_at=operation.next_attempt_at)
    _append_event_locked(operation, 'operation.retry_requested', payload={
        'attempt': operation.attempt_count + 1,
    })
    return operation


@transaction.atomic
def request_operation_cancel(operation_id, *, user=None) -> AsyncOperation:
    queryset = AsyncOperation.objects.select_for_update().filter(pk=operation_id)
    if user is not None:
        queryset = queryset.filter(user=user)
    operation = queryset.get()
    if operation.status in TERMINAL_STATUSES:
        return operation
    now = timezone.now()
    operation.status = AsyncOperation.Status.CANCELED
    operation.cancel_requested_at = now
    operation.completed_at = now
    operation.retryable = False
    operation.lease_owner = ''
    operation.lease_expires_at = None
    operation.fencing_token += 1
    operation.version += 1
    operation.save(update_fields=[
        'status', 'cancel_requested_at', 'completed_at', 'retryable', 'lease_owner',
        'lease_expires_at', 'fencing_token', 'version', 'updated_at',
    ])
    OperationDispatchOutbox.objects.filter(
        operation=operation,
        status__in=[
            OperationDispatchOutbox.Status.PENDING,
            OperationDispatchOutbox.Status.PUBLISHING,
            OperationDispatchOutbox.Status.FAILED,
        ],
    ).update(
        status=OperationDispatchOutbox.Status.CANCELED,
        locked_at=None,
        updated_at=now,
    )
    _append_event_locked(operation, 'operation.canceled')
    return operation


@transaction.atomic
def mark_dispatch_dead(operation_id, *, error_code='dispatch_dead', error_message='') -> AsyncOperation:
    operation = AsyncOperation.objects.select_for_update().get(pk=operation_id)
    if operation.status in TERMINAL_STATUSES:
        return operation
    operation.status = AsyncOperation.Status.FAILED
    operation.error_code = str(error_code)[:120]
    operation.error_message = str(error_message)[:2000]
    operation.retryable = False
    operation.completed_at = timezone.now()
    operation.next_attempt_at = None
    operation.lease_owner = ''
    operation.lease_expires_at = None
    operation.fencing_token += 1
    operation.version += 1
    operation.save(update_fields=[
        'status', 'error_code', 'error_message', 'retryable', 'completed_at',
        'next_attempt_at', 'lease_owner', 'lease_expires_at', 'fencing_token',
        'version', 'updated_at',
    ])
    _append_event_locked(operation, 'operation.failed', payload={'error_code': operation.error_code})
    return operation


def recover_stale_operations(*, batch_size: int = 200, now=None) -> dict[str, int]:
    now = now or timezone.now()
    candidate_ids = list(
        AsyncOperation.objects.filter(
            Q(status__in=ACTIVE_STATUSES, lease_expires_at__lte=now)
            | Q(status=AsyncOperation.Status.CANCEL_REQUESTED)
        ).order_by('lease_expires_at', 'created_at').values_list('id', flat=True)[: max(1, min(batch_size, 1000))]
    )
    retried = 0
    failed = 0
    canceled = 0
    for operation_id in candidate_ids:
        with transaction.atomic():
            operation = AsyncOperation.objects.select_for_update(skip_locked=True).filter(pk=operation_id).first()
            if not operation:
                continue
            uses_generic_dispatch = operation.dispatches.exists()
            if operation.status == AsyncOperation.Status.CANCEL_REQUESTED:
                operation.status = AsyncOperation.Status.CANCELED
                operation.completed_at = now
                canceled += 1
                event_type = 'operation.canceled'
            elif operation.status not in ACTIVE_STATUSES or not operation.lease_expires_at or operation.lease_expires_at > now:
                continue
            elif operation.attempt_count < operation.max_attempts:
                operation.status = AsyncOperation.Status.RETRYING
                operation.next_attempt_at = now
                operation.retryable = True
                operation.error_code = 'operation_lease_expired'
                operation.completed_at = None
                retried += 1
                event_type = 'operation.recovered'
            else:
                operation.status = AsyncOperation.Status.FAILED
                operation.retryable = False
                operation.error_code = 'operation_lease_expired'
                operation.completed_at = now
                failed += 1
                event_type = 'operation.failed'
            operation.lease_owner = ''
            operation.lease_expires_at = None
            operation.fencing_token += 1
            operation.version += 1
            operation.save(update_fields=[
                'status', 'next_attempt_at', 'retryable', 'error_code', 'completed_at',
                'lease_owner', 'lease_expires_at', 'fencing_token', 'version', 'updated_at',
            ])
            if operation.status == AsyncOperation.Status.RETRYING and uses_generic_dispatch:
                _create_dispatch_generation_locked(operation, available_at=now)
            _append_event_locked(operation, event_type, payload={'attempt': operation.attempt_count})
    return {'recovered': retried, 'failed': failed, 'canceled': canceled}


def normalize_handler_result(value: OperationHandlerResult | dict[str, Any] | None) -> OperationHandlerResult:
    if value is None:
        return OperationHandlerResult()
    if isinstance(value, OperationHandlerResult):
        return value
    if not isinstance(value, dict):
        raise TerminalOperationError('operation_handler_invalid_result')
    return OperationHandlerResult(
        result_type=str(value.get('result_type') or '')[:80],
        result_id=str(value.get('result_id') or '')[:120],
        result=value.get('result') if isinstance(value.get('result'), dict) else {},
        metadata=value.get('metadata') if isinstance(value.get('metadata'), dict) else {},
    )
