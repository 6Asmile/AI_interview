from celery import shared_task
from django.db import models, transaction
from django.utils import timezone

from .models import Notification, NotificationOutbox


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def publish_notification_outbox(self, event_id=None, limit=100):
    ids = [event_id] if event_id else list(
        NotificationOutbox.objects.filter(status__in=[NotificationOutbox.Status.PENDING, NotificationOutbox.Status.FAILED])
        .order_by('created_at').values_list('event_id', flat=True)[:limit]
    )
    published = 0
    for current_id in ids:
        try:
            with transaction.atomic():
                event = NotificationOutbox.objects.select_for_update().get(event_id=current_id)
                if event.notification_id:
                    continue
                notification = Notification.objects.create(
                    recipient=event.recipient,
                    actor_content_type=event.actor_content_type,
                    actor_object_id=event.actor_object_id,
                    verb=event.verb,
                    target_content_type=event.target_content_type,
                    target_object_id=event.target_object_id,
                    action_object_content_type=event.action_object_content_type,
                    action_object_object_id=event.action_object_object_id,
                )
                event.notification = notification
                event.status = NotificationOutbox.Status.PUBLISHED
                event.published_at = timezone.now()
                event.last_error = ''
                event.attempts += 1
                event.save(update_fields=['notification', 'status', 'published_at', 'last_error', 'attempts'])
                published += 1
        except NotificationOutbox.DoesNotExist:
            continue
        except Exception as exc:
            NotificationOutbox.objects.filter(event_id=current_id).update(
                status=NotificationOutbox.Status.FAILED,
                last_error=str(exc)[:2000],
                attempts=models.F('attempts') + 1,
            )
            if event_id:
                raise self.retry(exc=exc)
    return {'published': published}


@shared_task
def create_notification_task(recipient_id, actor_ct_id, actor_id, verb, **kwargs):
    event = NotificationOutbox.objects.create(
        recipient_id=recipient_id,
        actor_content_type_id=actor_ct_id,
        actor_object_id=str(actor_id),
        verb=verb,
        target_content_type_id=kwargs.get('target_ct_id'),
        target_object_id=kwargs.get('target_id'),
        action_object_content_type_id=kwargs.get('action_object_ct_id'),
        action_object_object_id=kwargs.get('action_object_id'),
    )
    return publish_notification_outbox(str(event.event_id))
