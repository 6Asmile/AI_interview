# ai_interview_backend/interviews/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import EvaluationRun, InterviewSession


# @shared_task 装饰器让这个函数成为一个 Celery 任务，
# 并且它不依赖于任何特定的 Celery app 实例，可复用性好。
@shared_task
def cleanup_stale_interviews(apply=False):
    """
    一个定时任务，用于将超过半小时未活动的“进行中”面试标记为“已取消”。
    """
    # 定义超时阈值为半小时前
    timeout_threshold = timezone.now() - timedelta(hours=2)

    # 查找所有状态为 'running' 且最后更新时间在2小时前的面试会话
    # `updated_at__lt` 的意思是 "updated_at less than"
    stale_sessions = InterviewSession.objects.filter(
        status=InterviewSession.Status.RUNNING,
        last_activity_at__lt=timeout_threshold
    )

    stale_ids = list(stale_sessions.values_list('id', flat=True))
    if not apply:
        return {'dry_run': True, 'stale_count': len(stale_ids), 'session_ids': [str(item) for item in stale_ids[:100]]}
    now = timezone.now()
    updated_count = stale_sessions.update(
        status=InterviewSession.Status.CANCELED,
        finished_at=now,
        last_activity_at=now,
    )
    return {'dry_run': False, 'stale_count': len(stale_ids), 'updated_count': updated_count}


@shared_task
def run_evaluation_run(run_id: int):
    from .evaluation import run_offline_rule_evaluation

    run = EvaluationRun.objects.get(id=run_id)
    return run_offline_rule_evaluation(run).summary
