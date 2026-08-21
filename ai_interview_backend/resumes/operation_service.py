from __future__ import annotations

from django.conf import settings
from django.db import transaction

from core.operations import create_operation_with_dispatch

from .models import ResumeOperationRequest
from .schema import sha256_json


_QUEUE_POLICY = {
    'resume.preview': ('CELERY_RESUME_RENDER_QUEUE', 'resume.render', 3),
    'resume.export': ('CELERY_RESUME_RENDER_QUEUE', 'resume.render', 3),
    'resume.share_export': ('CELERY_RESUME_RENDER_QUEUE', 'resume.render', 3),
    'resume.quality_review': ('CELERY_AGENT_QUEUE', 'agent.interactive', 3),
    'resume.import': ('CELERY_DOCUMENT_QUEUE', 'documents', 5),
    'resume.import.retry': ('CELERY_DOCUMENT_QUEUE', 'documents', 5),
    'resume.suggestion': ('CELERY_AGENT_QUEUE', 'agent.interactive', 3),
}


@transaction.atomic
def create_resume_operation(
    *,
    user,
    resume,
    operation_type: str,
    title: str,
    artifact=None,
    import_job=None,
    quality_report=None,
    base_version=None,
    task_key: str = '',
    instruction: str = '',
    job_target_id=None,
):
    """Persist a private input snapshot and durable dispatch in one commit."""

    if operation_type not in _QUEUE_POLICY:
        raise ValueError(f'unsupported_resume_operation:{operation_type}')
    instruction = str(instruction or '')[:4000]
    snapshot = {
        'operation_type': operation_type,
        'resume_id': resume.pk,
        'artifact_id': str(artifact.pk) if artifact else None,
        'import_job_id': import_job.pk if import_job else None,
        'quality_report_id': quality_report.pk if quality_report else None,
        'base_version_id': base_version.pk if base_version else None,
        'task_key': str(task_key or ''),
        'instruction': instruction,
        'job_target_id': job_target_id,
    }
    request_snapshot = ResumeOperationRequest.objects.create(
        user=user,
        resume=resume,
        operation_type=operation_type,
        artifact=artifact,
        import_job=import_job,
        quality_report=quality_report,
        base_version=base_version,
        task_key=str(task_key or '')[:80],
        instruction=instruction,
        job_target_id=job_target_id,
        input_hash=sha256_json(snapshot),
    )
    setting_name, routing_key, max_attempts = _QUEUE_POLICY[operation_type]
    queue = str(getattr(settings, setting_name, routing_key))
    metadata = {
        'resume_id': resume.pk,
        'request_id': str(request_snapshot.pk),
    }
    if artifact:
        metadata['artifact_id'] = str(artifact.pk)
    if import_job:
        metadata['import_job_id'] = import_job.pk
    if quality_report:
        metadata['quality_report_id'] = quality_report.pk
    if base_version:
        metadata['base_version_id'] = base_version.pk
    if task_key:
        metadata['task_key'] = str(task_key)[:80]
    operation = create_operation_with_dispatch(
        user=user,
        operation_type=operation_type,
        source_app='resumes',
        source_model='ResumeOperationRequest',
        source_id=str(request_snapshot.pk),
        title=title,
        input_type='ResumeOperationRequest',
        input_id=str(request_snapshot.pk),
        input_version='1',
        input_hash=request_snapshot.input_hash,
        metadata=metadata,
        max_attempts=max_attempts,
        queue=queue,
        routing_key=routing_key,
    )
    return operation, request_snapshot
