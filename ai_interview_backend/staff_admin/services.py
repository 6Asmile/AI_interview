import json

from django.conf import settings
from django.db import transaction

from .models import StaffEmailOutbox, StaffInvitation
from .security import encrypt_secret


def enqueue_staff_invitation_email(invitation: StaffInvitation, raw_token: str):
    activation_url = f"{str(settings.PUBLIC_ADMIN_URL).rstrip('/')}/register?invite={raw_token}"
    payload = {
        'activation_url': activation_url,
        'display_name': invitation.account.display_name,
        'expires_at': invitation.expires_at.isoformat(),
    }
    event = StaffEmailOutbox.objects.create(
        invitation=invitation,
        to_email=invitation.account.email,
        encrypted_payload=encrypt_secret(json.dumps(payload, ensure_ascii=False)),
    )
    from .tasks import publish_staff_email_outbox
    transaction.on_commit(lambda: publish_staff_email_outbox.delay(str(event.id)))
    return event, activation_url
