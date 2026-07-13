from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone

from .models import ChatOutbox


@shared_task
def publish_pending_chat_outbox(limit: int = 100):
    layer = get_channel_layer()
    published = 0
    for event in ChatOutbox.objects.filter(status__in=[ChatOutbox.Status.PENDING, ChatOutbox.Status.FAILED]).order_by('created_at')[:limit]:
        try:
            async_to_sync(layer.group_send)(event.topic, {'type': 'broadcast_chat_message', 'message': event.payload})
            event.status = ChatOutbox.Status.PUBLISHED
            event.published_at = timezone.now()
            event.last_error = ''
            published += 1
        except Exception as exc:
            event.status = ChatOutbox.Status.FAILED
            event.last_error = str(exc)[:2000]
        event.attempts += 1
        event.save(update_fields=['status', 'published_at', 'last_error', 'attempts'])
    return {'published': published}
