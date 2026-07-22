from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import NotificationOutbox


def enqueue_notification(*, recipient, actor, verb, target=None, action_object=None):
    event = NotificationOutbox.objects.create(
        recipient=recipient,
        actor_content_type=ContentType.objects.get_for_model(actor, for_concrete_model=False),
        actor_object_id=str(actor.pk),
        verb=verb,
        target_content_type=ContentType.objects.get_for_model(target, for_concrete_model=False) if target else None,
        target_object_id=str(target.pk) if target else None,
        action_object_content_type=ContentType.objects.get_for_model(action_object, for_concrete_model=False) if action_object else None,
        action_object_object_id=str(action_object.pk) if action_object else None,
    )
    from .tasks import publish_notification_outbox
    transaction.on_commit(lambda: publish_notification_outbox.delay(str(event.event_id)))
    return event
