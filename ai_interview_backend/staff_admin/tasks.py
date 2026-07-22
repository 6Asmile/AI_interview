import json

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone

from .models import StaffEmailOutbox, StaffInvitation
from .security import decrypt_secret


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def publish_staff_email_outbox(self, event_id=None, limit=50):
    ids = [event_id] if event_id else list(
        StaffEmailOutbox.objects.filter(status__in=[StaffEmailOutbox.Status.PENDING, StaffEmailOutbox.Status.FAILED])
        .order_by('created_at').values_list('id', flat=True)[:limit]
    )
    sent = 0
    for current_id in ids:
        try:
            with transaction.atomic():
                event = StaffEmailOutbox.objects.select_for_update().select_related('invitation__account').get(pk=current_id)
                if event.status == StaffEmailOutbox.Status.SENT:
                    continue
                invitation = event.invitation
                if invitation.status != StaffInvitation.Status.PENDING or invitation.expires_at <= timezone.now():
                    event.status = StaffEmailOutbox.Status.FAILED
                    event.last_error = 'invitation_not_active'
                    event.attempts += 1
                    event.save(update_fields=['status', 'last_error', 'attempts'])
                    continue
                payload = json.loads(decrypt_secret(event.encrypted_payload))
                send_mail(
                    subject='iFaceoff 员工管理端邀请',
                    message=(
                        f"{payload.get('display_name') or '你好'}，\n\n"
                        '你已被邀请加入 iFaceoff 企业运营管理后台。请在有效期内打开以下地址完成密码和 MFA 设置：\n\n'
                        f"{payload['activation_url']}\n\n"
                        f"邀请有效期至：{payload['expires_at']}\n"
                        '如果你不认识邀请人，请忽略此邮件。'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL or 'no-reply@ifaceoff.local',
                    recipient_list=[event.to_email],
                    fail_silently=False,
                )
                now = timezone.now()
                event.status = StaffEmailOutbox.Status.SENT
                event.sent_at = now
                event.attempts += 1
                event.last_error = ''
                event.encrypted_payload = ''
                event.save(update_fields=['status', 'sent_at', 'attempts', 'last_error', 'encrypted_payload'])
                invitation.sent_count = models.F('sent_count') + 1
                invitation.last_sent_at = now
                invitation.save(update_fields=['sent_count', 'last_sent_at'])
                sent += 1
        except StaffEmailOutbox.DoesNotExist:
            continue
        except Exception as exc:
            StaffEmailOutbox.objects.filter(pk=current_id).update(
                status=StaffEmailOutbox.Status.FAILED,
                last_error=str(exc)[:2000],
                attempts=models.F('attempts') + 1,
            )
            if event_id:
                raise self.retry(exc=exc)
    return {'sent': sent}
