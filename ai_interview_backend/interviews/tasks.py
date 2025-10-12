# ai_interview_backend/interviews/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import InterviewSession


# @shared_task 装饰器让这个函数成为一个 Celery 任务，
# 并且它不依赖于任何特定的 Celery app 实例，可复用性好。
@shared_task
def cleanup_stale_interviews():
    """
    一个定时任务，用于将超过2小时未活动的“进行中”面试标记为“已取消”。
    """
    # 定义超时阈值为2小时前
    timeout_threshold = timezone.now() - timedelta(hours=2)

    # 查找所有状态为 'running' 且最后更新时间在2小时前的面试会话
    # `updated_at__lt` 的意思是 "updated_at less than"
    stale_sessions = InterviewSession.objects.filter(
        status=InterviewSession.Status.RUNNING,
        updated_at__lt=timeout_threshold
    )

    # 只有在确实找到了超时的会话时才执行更新
    if stale_sessions.exists():
        count = stale_sessions.count()
        print(f"Celery 任务：找到 {count} 个超时的面试会话，正在清理...")

        # 使用 .update() 进行批量更新，性能远高于循环 .save()
        updated_count = stale_sessions.update(status=InterviewSession.Status.CANCELED)

        print(f"Celery 任务：成功将 {updated_count} 个会话的状态更新为 'canceled'。")
        return f"成功清理了 {updated_count} 个超时的面试会话。"
    else:
        print("Celery 任务：没有发现需要清理的超时面试会话。")
        return "没有超时的面试会话。"