from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from .models import ConsumerInbox, IntegrationOutbox


EventHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
_handlers: dict[str, list['RegisteredHandler']] = defaultdict(list)


@dataclass(frozen=True)
class RegisteredHandler:
    consumer_name: str
    event_type: str
    callback: EventHandler


def register_event_handler(event_type: str, consumer_name: str):
    """Register an in-process projector behind the durable Celery consumer."""

    def decorator(callback: EventHandler):
        _handlers[event_type].append(RegisteredHandler(consumer_name, event_type, callback))
        return callback

    return decorator


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    value = json.loads(json.dumps(payload or {}, ensure_ascii=False, default=str))
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) > 64 * 1024:
        raise ValueError('integration_event_payload_too_large')
    forbidden = {'resume_content', 'answer_text', 'document_content', 'api_key', 'secret'}
    if forbidden.intersection(value):
        raise ValueError('integration_event_contains_forbidden_sensitive_field')
    return value


def enqueue_integration_event(
    *,
    event_type: str,
    producer: str,
    aggregate_type: str,
    aggregate_id: str | int | uuid.UUID,
    payload: dict[str, Any] | None = None,
    tenant_id: str | int | uuid.UUID | None = None,
    actor_id: str | int | uuid.UUID | None = None,
    correlation_id: uuid.UUID | str | None = None,
    causation_id: uuid.UUID | str | None = None,
    trace_id: str = '',
    privacy_class: str = IntegrationOutbox.PrivacyClass.INTERNAL,
    event_version: int = 1,
) -> IntegrationOutbox:
    """Persist an event in the caller's transaction; never publishes inline."""

    return IntegrationOutbox.objects.create(
        event_type=event_type,
        event_version=max(1, int(event_version)),
        producer=producer,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        tenant_id=str(tenant_id or ''),
        actor_id=str(actor_id or ''),
        correlation_id=uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4(),
        causation_id=uuid.UUID(str(causation_id)) if causation_id else None,
        trace_id=str(trace_id or '')[:64],
        privacy_class=privacy_class,
        payload=_safe_payload(payload),
        available_at=timezone.now(),
    )


def event_envelope(event: IntegrationOutbox) -> dict[str, Any]:
    return {
        'event_id': str(event.event_id),
        'event_type': event.event_type,
        'event_version': event.event_version,
        'occurred_at': event.created_at.isoformat(),
        'producer': event.producer,
        'aggregate_type': event.aggregate_type,
        'aggregate_id': event.aggregate_id,
        'tenant_id': event.tenant_id or None,
        'actor_id': event.actor_id or None,
        'correlation_id': str(event.correlation_id),
        'causation_id': str(event.causation_id) if event.causation_id else None,
        'trace_id': event.trace_id,
        'privacy_class': event.privacy_class,
        'payload': event.payload,
    }


def _payload_hash(envelope: dict[str, Any]) -> str:
    encoded = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def consume_event(envelope: dict[str, Any]) -> dict[str, Any]:
    """Run all registered projectors with one inbox fence per projector."""

    event_type = str(envelope.get('event_type') or '')
    event_id = uuid.UUID(str(envelope['event_id']))
    handlers = [*_handlers.get(event_type, []), *_handlers.get('*', [])]
    outcomes: dict[str, Any] = {}
    for handler in handlers:
        payload_hash = _payload_hash(envelope)
        with transaction.atomic():
            inbox, created = ConsumerInbox.objects.select_for_update().get_or_create(
                consumer_name=handler.consumer_name,
                event_id=event_id,
                defaults={
                    'event_type': event_type,
                    'event_version': int(envelope.get('event_version') or 1),
                    'payload_hash': payload_hash,
                },
            )
            if not created:
                if inbox.payload_hash != payload_hash:
                    raise ValueError('consumer_inbox_payload_mismatch')
                if inbox.status == ConsumerInbox.Status.PROCESSED:
                    outcomes[handler.consumer_name] = {'replayed': True, **(inbox.result or {})}
                    continue
                inbox.status = ConsumerInbox.Status.PROCESSING
                inbox.attempts += 1
                inbox.last_error = ''
                inbox.save(update_fields=['status', 'attempts', 'last_error', 'updated_at'])
        try:
            result = handler.callback(envelope) or {}
        except Exception as exc:
            ConsumerInbox.objects.filter(pk=inbox.pk).update(
                status=ConsumerInbox.Status.FAILED,
                last_error=f'{type(exc).__name__}: {exc}'[:2000],
            )
            raise
        ConsumerInbox.objects.filter(pk=inbox.pk).update(
            status=ConsumerInbox.Status.PROCESSED,
            result=result,
            processed_at=timezone.now(),
            last_error='',
        )
        outcomes[handler.consumer_name] = result
    return outcomes


def retry_delay(attempts: int) -> timedelta:
    seconds = min(1800, 2 ** min(max(1, attempts), 10))
    return timedelta(seconds=seconds)
