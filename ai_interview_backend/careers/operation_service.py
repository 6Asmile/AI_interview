from __future__ import annotations

from django.conf import settings
from django.db import transaction

from core.operations import create_operation_with_dispatch

from .services import stable_hash


@transaction.atomic
def create_job_match_operation(*, analysis, title: str, metadata=None):
    """Bind a frozen match analysis to its durable operation and dispatch."""

    if analysis.operation_id:
        raise ValueError('job_match_operation_already_bound')
    input_hash = stable_hash({
        'analysis_id': str(analysis.pk),
        'resume_version_id': analysis.resume_version_id,
        'jd_snapshot_hash': analysis.jd_snapshot_hash,
        'config_hash': analysis.config_hash,
    })
    operation = create_operation_with_dispatch(
        user=analysis.user,
        operation_type='career.job_match',
        source_app='careers',
        source_model='JobMatchAnalysis',
        source_id=str(analysis.pk),
        title=title,
        input_type='JobMatchAnalysis',
        input_id=str(analysis.pk),
        input_version='1',
        input_hash=input_hash,
        metadata={
            'analysis_id': str(analysis.pk),
            'job_target_id': analysis.job_target_id,
            'resume_version_id': analysis.resume_version_id,
            **(metadata or {}),
        },
        max_attempts=4,
        queue=str(getattr(settings, 'CELERY_CAREER_QUEUE', 'career.analysis')),
        routing_key='career.analysis',
    )
    analysis.operation = operation
    analysis.save(update_fields=['operation'])
    return operation
