from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .events import consume_event, event_envelope, retry_delay
from .models import IntegrationOutbox


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
    return consume_event(envelope)


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
                queue='events',
                exchange='ifaceoff.events',
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
