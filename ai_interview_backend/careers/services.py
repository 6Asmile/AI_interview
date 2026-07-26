import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.events import enqueue_integration_event

from .models import (
    CareerTimelineEvent,
    JobPosting,
    JobTarget,
    LearningPlan,
    LearningTask,
)


def stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def record_timeline_event(
    *,
    user,
    event_type: str,
    title: str,
    source_type: str,
    source_id,
    summary: str = '',
    metadata: dict | None = None,
    occurred_at=None,
):
    dedup_key = f'{event_type}:{source_type}:{source_id}'
    event, _ = CareerTimelineEvent.objects.get_or_create(
        user=user,
        dedup_key=dedup_key,
        defaults={
            'event_type': event_type,
            'title': title,
            'summary': summary,
            'source_type': source_type,
            'source_id': str(source_id),
            'metadata': metadata or {},
            'occurred_at': occurred_at or timezone.now(),
        },
    )
    return event


@transaction.atomic
def save_posting_as_target(*, posting: JobPosting, user) -> JobTarget:
    revision = posting.current_revision
    if posting.status != JobPosting.Status.PUBLISHED or not revision:
        raise ValueError('岗位尚未发布。')
    target, created = JobTarget.objects.get_or_create(
        user=user,
        job_posting=posting,
        job_posting_revision=revision,
        defaults={
            'source_type': JobTarget.SourceType.COMPANY,
            'company_name': posting.company.name,
            'position_name': revision.title,
            'jd_text': revision.jd_text,
            'location': posting.location,
            'keywords': revision.skills,
            'jd_snapshot_hash': revision.content_hash,
        },
    )
    if created:
        record_timeline_event(
            user=user,
            event_type='job.saved',
            title=f'保存岗位：{target.position_name}',
            source_type='JobTarget',
            source_id=target.pk,
            metadata={'company_id': str(posting.company_id), 'job_posting_id': str(posting.pk)},
        )
        enqueue_integration_event(
            event_type='job.saved',
            producer='careers',
            aggregate_type='JobTarget',
            aggregate_id=target.pk,
            actor_id=user.pk,
            payload={'job_target_id': target.pk, 'job_posting_id': str(posting.pk)},
        )
    return target


@transaction.atomic
def create_learning_plan(*, analysis, user) -> LearningPlan:
    if analysis.user_id != user.id:
        raise PermissionError('不能读取其他用户的匹配分析。')
    if analysis.status != analysis.Status.SUCCEEDED:
        raise ValueError('匹配分析尚未完成。')
    plan, created = LearningPlan.objects.get_or_create(
        user=user,
        match_analysis=analysis,
        defaults={
            'job_target': analysis.job_target,
            'title': f'{analysis.job_target.position_name} 补强计划',
            'summary': '根据岗位差距生成，完成后可再次进行岗位匹配或专项模拟面试。',
            'source_type': 'job_match_analysis',
            'source_id': str(analysis.pk),
            'config_snapshot': analysis.config_snapshot,
        },
    )
    if not created:
        return plan
    gaps = list(analysis.gaps or [])[:12]
    for index, gap in enumerate(gaps):
        label = gap.get('name') if isinstance(gap, dict) else str(gap)
        LearningTask.objects.create(
            user=user,
            plan=plan,
            title=f'补强：{label}',
            dimension='job_gap',
            priority=LearningTask.Priority.HIGH if index < 3 else LearningTask.Priority.MEDIUM,
            evidence_refs=[{'type': 'JobMatchAnalysis', 'id': str(analysis.pk)}],
            source_type='job_match_analysis',
            source_id=str(analysis.pk),
        )
    record_timeline_event(
        user=user,
        event_type='learning.plan.created',
        title=plan.title,
        source_type='LearningPlan',
        source_id=plan.pk,
        metadata={'match_analysis_id': str(analysis.pk), 'task_count': len(gaps)},
    )
    enqueue_integration_event(
        event_type='learning.plan.created',
        producer='careers',
        aggregate_type='LearningPlan',
        aggregate_id=plan.pk,
        actor_id=user.pk,
        payload={'learning_plan_id': str(plan.pk), 'match_analysis_id': str(analysis.pk)},
    )
    return plan
