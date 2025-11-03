from celery import shared_task
from .models import Notification

@shared_task
def create_notification_task(recipient_id, actor_ct_id, actor_id, verb, **kwargs):
    # ... 在这里执行 Notification.objects.create(...) 的逻辑 ...
    # 这样可以避免阻塞主请求线程，并将通知创建与 RabbitMQ 集成
    pass