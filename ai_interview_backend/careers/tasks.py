from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.events import enqueue_integration_event
from core.models import AsyncOperation
from resumes.fit_score import RULE_VERSION, calculate_resume_fit

from .models import CareerTimelineEvent, JobApplication, JobMatchAnalysis, LearningTask, WeeklyCareerReport
from .services import record_timeline_event, stable_hash


def execute_job_match_analysis(analysis: JobMatchAnalysis, *, legacy_operation=None):
    """Execute the domain transition without owning the unified Operation.

    ``legacy_operation`` exists only for already-published direct Celery
    messages. Registered operation handlers always pass ``None`` and the core
    worker exclusively owns operation state, retries, fencing and completion.
    """

    if analysis.status == JobMatchAnalysis.Status.SUCCEEDED:
        return {'analysis_id': str(analysis.pk), 'status': analysis.status}
    JobMatchAnalysis.objects.filter(pk=analysis.pk).update(status=JobMatchAnalysis.Status.RUNNING)
    if legacy_operation:
        AsyncOperation.objects.filter(pk=legacy_operation.pk).update(
            status=AsyncOperation.Status.RUNNING,
            progress=10,
            started_at=timezone.now(),
        )
    try:
        result = calculate_resume_fit(
            analysis.resume_version.resume_json,
            analysis.jd_snapshot,
            analysis.resume_version.evidence_snapshot,
        )
        config_snapshot = {
            'engine': RULE_VERSION,
            'prompt_revision': None,
            'model_alias': None,
            'degraded': False,
        }
        recommendations = [
            {'type': 'resume_candidate', 'message': f'补充“{item}”相关的真实、可核验证据。'}
            for item in result['missing_keywords']
        ]
        now = timezone.now()
        with transaction.atomic():
            JobMatchAnalysis.objects.filter(pk=analysis.pk).update(
                status=JobMatchAnalysis.Status.SUCCEEDED,
                score=result['score'],
                dimensions=result['breakdown'],
                matched_skills=result['matched_keywords'],
                gaps=result['missing_keywords'],
                evidence_refs=analysis.resume_version.evidence_snapshot,
                recommendations=recommendations,
                config_snapshot=config_snapshot,
                config_hash=stable_hash(config_snapshot),
                completed_at=now,
            )
            if legacy_operation:
                AsyncOperation.objects.filter(pk=legacy_operation.pk).update(
                    status=AsyncOperation.Status.SUCCEEDED,
                    progress=100,
                    metadata={'result_type': 'JobMatchAnalysis', 'result_id': str(analysis.pk)},
                    completed_at=now,
                )
            record_timeline_event(
                user=analysis.user,
                event_type='job.match.completed',
                title=f'完成岗位匹配：{analysis.job_target.position_name}',
                source_type='JobMatchAnalysis',
                source_id=analysis.pk,
                metadata={'score': result['score'], 'job_target_id': analysis.job_target_id},
                occurred_at=now,
            )
            enqueue_integration_event(
                event_type='job.match.completed',
                producer='careers',
                aggregate_type='JobMatchAnalysis',
                aggregate_id=analysis.pk,
                actor_id=analysis.user_id,
                payload={
                    'analysis_id': str(analysis.pk),
                    'job_target_id': analysis.job_target_id,
                    'status': JobMatchAnalysis.Status.SUCCEEDED,
                    'score': result['score'],
                },
            )
        return {'analysis_id': str(analysis.pk), 'status': JobMatchAnalysis.Status.SUCCEEDED}
    except Exception as exc:
        now = timezone.now()
        JobMatchAnalysis.objects.filter(pk=analysis.pk).update(
            status=JobMatchAnalysis.Status.FAILED,
            error_code=type(exc).__name__[:120],
            completed_at=now,
        )
        if legacy_operation:
            AsyncOperation.objects.filter(pk=legacy_operation.pk).update(
                status=AsyncOperation.Status.FAILED,
                progress=100,
                error_code=type(exc).__name__[:120],
                error_message=str(exc)[:2000],
                retryable=isinstance(exc, (ConnectionError, TimeoutError)),
                completed_at=now,
            )
        raise


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=150,
    time_limit=180,
)
def run_job_match_analysis(self, analysis_id: str, operation_id='linked'):
    analysis = JobMatchAnalysis.objects.select_related(
        'user', 'job_target', 'resume_version', 'operation',
    ).get(pk=analysis_id)
    if operation_id == 'linked':
        legacy_operation = analysis.operation
    elif operation_id:
        legacy_operation = AsyncOperation.objects.filter(pk=operation_id).first()
    else:
        legacy_operation = None
    return execute_job_match_analysis(analysis, legacy_operation=legacy_operation)


@shared_task
def generate_weekly_career_reports():
    from datetime import timedelta
    from users.models import User

    period_end = timezone.localdate()
    period_start = period_end - timedelta(days=6)
    created = 0
    users = User.objects.filter(
        career_timeline_events__occurred_at__date__gte=period_start,
    ).distinct()
    for user in users.iterator():
        events = CareerTimelineEvent.objects.filter(
            user=user,
            occurred_at__date__range=(period_start, period_end),
        )
        metrics = {
            'effective_events': events.count(),
            'applications_updated': events.filter(event_type='application.status.changed').count(),
            'interviews_completed': events.filter(event_type='interview.completed').count(),
            'learning_tasks_completed': events.filter(event_type='learning.task.completed').count(),
            'job_matches_completed': events.filter(event_type='job.match.completed').count(),
        }
        open_tasks = LearningTask.objects.filter(user=user).exclude(status=LearningTask.Status.DONE).count()
        active_applications = JobApplication.objects.filter(user=user).exclude(
            status__in=[JobApplication.Status.REJECTED, JobApplication.Status.WITHDRAWN],
        ).count()
        _, was_created = WeeklyCareerReport.objects.update_or_create(
            user=user,
            period_start=period_start,
            defaults={
                'period_end': period_end,
                'metrics': metrics,
                'insights': [f'本周记录了 {metrics["effective_events"]} 次有效成长行为。'],
                'next_actions': [
                    f'继续完成 {open_tasks} 个补强任务。',
                    f'更新 {active_applications} 个进行中的投递。',
                ],
                'config_hash': stable_hash({'rule': 'weekly-career-report/1.0'}),
            },
        )
        created += int(was_created)
    return {'created': created, 'period_start': str(period_start), 'period_end': str(period_end)}
