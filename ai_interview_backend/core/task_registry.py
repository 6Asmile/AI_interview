from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AsyncOperation


STATUS_MAP = {
    'pending': AsyncOperation.Status.PENDING,
    'uploading': AsyncOperation.Status.RUNNING,
    'processing': AsyncOperation.Status.RUNNING,
    'parsing': AsyncOperation.Status.RUNNING,
    'indexing': AsyncOperation.Status.RUNNING,
    'merging': AsyncOperation.Status.RUNNING,
    'review_required': AsyncOperation.Status.REVIEW_REQUIRED,
    'completed': AsyncOperation.Status.SUCCEEDED,
    'confirmed': AsyncOperation.Status.SUCCEEDED,
    'indexed': AsyncOperation.Status.SUCCEEDED,
    'merged': AsyncOperation.Status.SUCCEEDED,
    'succeeded': AsyncOperation.Status.SUCCEEDED,
    'partial_failed': AsyncOperation.Status.FAILED,
    'failed': AsyncOperation.Status.FAILED,
    'canceled': AsyncOperation.Status.CANCELED,
}


@transaction.atomic
def register_operation(*, user, operation_type, source_app, source_model, source_id, title, status='pending', progress=0, error_message='', retryable=False, metadata=None):
    # The former database-wide source uniqueness constraint was too broad for
    # legitimate repeated Operations. Serialize only the legacy projection
    # adapter on its owner row so concurrent v1 list reads cannot fork it.
    type(user).objects.select_for_update().only('pk').get(pk=user.pk)
    normalized = STATUS_MAP.get(str(status), str(status))
    now = timezone.now()
    completed_at = timezone.now() if normalized in {
        AsyncOperation.Status.SUCCEEDED, AsyncOperation.Status.FAILED, AsyncOperation.Status.CANCELED,
    } else None
    is_active_projection = normalized in {
        AsyncOperation.Status.CLAIMED,
        AsyncOperation.Status.RUNNING,
    }
    lookup = {
        'user': user,
        'operation_type': operation_type,
        'source_app': source_app,
        'source_model': source_model,
        'source_id': str(source_id),
    }
    existing = AsyncOperation.objects.filter(**lookup).order_by('created_at').first()
    if existing:
        # A legacy source is only projected once.  Subsequent v1 list reads
        # must not overwrite the authoritative Operation state, revive a
        # cancellation, or manufacture heartbeats from mutable domain rows.
        return existing
    operation = AsyncOperation.objects.create(
        **lookup,
        title=title[:255],
        status=normalized,
        progress=max(0, min(100, int(progress or 0))),
        error_message=str(error_message or '')[:2000],
        retryable=bool(retryable),
        metadata=metadata or {},
        completed_at=completed_at,
        # Legacy task rows are create-once read projections rather than Core
        # workers. Keep their compatibility lease explicit so the active state
        # invariant is never bypassed while v1 readers are phased out.
        lease_owner='legacy-projection' if is_active_projection else '',
        lease_expires_at=now + timedelta(minutes=10) if is_active_projection else None,
        heartbeat_at=now if is_active_projection else None,
    )
    return operation


def sync_operations_for_user(user):
    from resumes.models import ResumeImportJob
    from knowledge.models import KnowledgeImportBatch
    from video_uploads.models import FileUploadTask, VideoTranscodeTask

    for job in ResumeImportJob.objects.filter(user=user).select_related('resume')[:100]:
        register_operation(
            user=user, operation_type='resume_import', source_app='resumes', source_model='ResumeImportJob',
            source_id=job.id, title=f'解析简历：{job.resume.title}', status=job.status,
            progress=100 if job.status in {job.Status.REVIEW_REQUIRED, job.Status.CONFIRMED} else (50 if job.status == job.Status.PROCESSING else 0),
            error_message=job.error_message, retryable=job.status == job.Status.FAILED,
            metadata={'resume_id': job.resume_id, 'parser_name': job.parser_name},
        )
    for batch in KnowledgeImportBatch.objects.filter(uploaded_by=user)[:100]:
        total = max(1, batch.total_files)
        progress = round(((batch.success_count + batch.failed_count) / total) * 100)
        register_operation(
            user=user, operation_type='knowledge_import', source_app='knowledge', source_model='KnowledgeImportBatch',
            source_id=batch.id, title=f'知识库导入（{batch.total_files} 个文件）', status=batch.status,
            progress=progress, error_message='；'.join(str(item.get('error', '')) for item in (batch.error_log or [])[:3]),
            retryable=batch.status in {batch.Status.FAILED, batch.Status.PARTIAL_FAILED},
            metadata={'success_count': batch.success_count, 'failed_count': batch.failed_count},
        )
    for upload in FileUploadTask.objects.filter(user=user)[:50]:
        register_operation(
            user=user, operation_type='video_upload', source_app='video_uploads', source_model='FileUploadTask',
            source_id=upload.id, title=f'上传录像：{upload.file_name}', status=upload.status,
            progress=upload.progress_percent, retryable=upload.status == upload.Status.FAILED,
            metadata={'file_size': upload.file_size},
        )
    for task in VideoTranscodeTask.objects.filter(user=user)[:50]:
        register_operation(
            user=user, operation_type='video_transcode', source_app='video_uploads', source_model='VideoTranscodeTask',
            source_id=task.id, title=f'处理录像：{task.original_file_name}', status=task.status,
            progress=task.progress, error_message=task.error_message, retryable=task.status == task.Status.FAILED,
        )


def can_retry_legacy_source(operation: AsyncOperation) -> bool:
    return (
        (
            operation.operation_type == 'interview.agent_turn'
            and operation.source_app == 'interviews'
            and operation.source_model == 'InterviewAgentExecution'
        )
        or (operation.source_app == 'resumes' and operation.source_model == 'ResumeImportJob')
        or (operation.source_app == 'knowledge' and operation.source_model == 'KnowledgeImportBatch')
        or (operation.source_app == 'video_uploads' and operation.source_model == 'VideoTranscodeTask')
    )


@transaction.atomic
def retry_legacy_operation_source(operation: AsyncOperation):
    """Forward a v1 retry into an allowlisted, durable Operation handler.

    This compatibility adapter deliberately does not reset domain state and
    never invokes Celery directly.  The new handler reloads and validates the
    database-owned input before performing an idempotent domain transition.
    """

    if (
        operation.operation_type == 'interview.agent_turn'
        and operation.source_app == 'interviews'
        and operation.source_model == 'InterviewAgentExecution'
    ):
        from interviews.models import InterviewAgentDispatch, InterviewAgentExecution

        locked_operation = AsyncOperation.objects.select_for_update().get(pk=operation.pk)
        if (
            locked_operation.status == AsyncOperation.Status.CANCELED
            or locked_operation.cancel_requested_at is not None
        ):
            raise ValueError('agent_operation_canceled')
        execution = InterviewAgentExecution.objects.select_for_update().filter(
            pk=locked_operation.source_id,
            operation=locked_operation,
        ).first()
        if not execution:
            raise ValueError('agent_execution_not_found')
        if execution.status == InterviewAgentExecution.Status.CANCELED:
            raise ValueError('agent_execution_canceled')
        if execution.status not in {
            InterviewAgentExecution.Status.FAILED_RETRYABLE,
            InterviewAgentExecution.Status.FAILED_TERMINAL,
        }:
            raise ValueError(f'agent_execution_not_retryable:{execution.status}')

        # Raise the execution fence before releasing all stale lease material.
        # A late worker holding the previous fence can no longer publish a
        # result after the manual retry has been accepted.
        execution.status = InterviewAgentExecution.Status.FAILED_RETRYABLE
        execution.completed_at = None
        execution.error_code = ''
        execution.fallback_reason = ''
        execution.lease_owner = ''
        execution.lease_expires_at = None
        execution.heartbeat_at = None
        execution.fencing_token += 1
        execution.version += 1
        execution.save(update_fields=[
            'status', 'completed_at', 'error_code', 'fallback_reason',
            'lease_owner', 'lease_expires_at', 'heartbeat_at', 'fencing_token',
            'version', 'updated_at',
        ])

        dispatch, _ = InterviewAgentDispatch.objects.select_for_update().get_or_create(
            execution=execution,
        )
        dispatch.status = InterviewAgentDispatch.Status.PENDING
        dispatch.attempts = 0
        dispatch.celery_task_id = ''
        dispatch.error_code = ''
        dispatch.error_message = ''
        dispatch.next_attempt_at = None
        dispatch.published_at = None
        dispatch.save(update_fields=[
            'status', 'attempts', 'celery_task_id', 'error_code', 'error_message',
            'next_attempt_at', 'published_at', 'updated_at',
        ])
        return locked_operation
    if operation.source_app == 'resumes' and operation.source_model == 'ResumeImportJob':
        from resumes.models import ResumeImportJob
        from resumes.operation_service import create_resume_operation

        job = ResumeImportJob.objects.get(pk=operation.source_id, user=operation.user)
        forwarded, _ = create_resume_operation(
            user=operation.user,
            resume=job.resume,
            operation_type='resume.import.retry',
            title=f'重试解析简历：{job.resume.title}',
            import_job=job,
        )
        return forwarded
    elif operation.source_app == 'knowledge' and operation.source_model == 'KnowledgeImportBatch':
        from knowledge.models import KnowledgeImportBatch, KnowledgeImportFile
        from knowledge.operation_handlers import IMPORT_OPERATION, create_knowledge_operation

        batch = KnowledgeImportBatch.objects.get(pk=operation.source_id, uploaded_by=operation.user)
        failed = list(batch.import_files.filter(status=KnowledgeImportFile.Status.FAILED))
        if not failed:
            raise ValueError('no_failed_import_files')
        forwarded = []
        for item in failed:
            forwarded.append(create_knowledge_operation(
                user=operation.user,
                operation_type=IMPORT_OPERATION,
                source_model='KnowledgeImportFile',
                source_id=item.id,
                title=f'重试导入知识文件：{item.original_name}',
                metadata={
                    'batch_id': str(batch.pk),
                    'legacy_operation_id': str(operation.pk),
                },
            ))
        return forwarded
    elif operation.source_app == 'video_uploads' and operation.source_model == 'VideoTranscodeTask':
        from video_uploads.models import VideoTranscodeTask
        from video_uploads.operation_handlers import create_video_operation

        task = VideoTranscodeTask.objects.select_related('upload_task').get(
            pk=operation.source_id,
            user=operation.user,
        )
        if not task.upload_task:
            raise ValueError('legacy_media_operation_requires_upload_snapshot')
        return create_video_operation(
            user=operation.user,
            upload_task=task.upload_task,
            transcode_task=task,
        )
    else:
        raise ValueError('operation_not_retryable')


def retry_operation(operation: AsyncOperation):
    """Legacy compatibility wrapper returning the authoritative forwarded row."""

    forwarded = retry_legacy_operation_source(operation)
    return forwarded[0] if isinstance(forwarded, list) else forwarded
