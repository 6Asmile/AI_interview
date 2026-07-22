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


def register_operation(*, user, operation_type, source_app, source_model, source_id, title, status='pending', progress=0, error_message='', retryable=False, metadata=None):
    normalized = STATUS_MAP.get(str(status), str(status))
    completed_at = timezone.now() if normalized in {
        AsyncOperation.Status.SUCCEEDED, AsyncOperation.Status.FAILED, AsyncOperation.Status.CANCELED,
    } else None
    operation, _ = AsyncOperation.objects.update_or_create(
        user=user,
        source_app=source_app,
        source_model=source_model,
        source_id=str(source_id),
        defaults={
            'operation_type': operation_type,
            'title': title[:255],
            'status': normalized,
            'progress': max(0, min(100, int(progress or 0))),
            'error_message': str(error_message or '')[:2000],
            'retryable': bool(retryable),
            'metadata': metadata or {},
            'completed_at': completed_at,
        },
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


def retry_operation(operation: AsyncOperation):
    if operation.source_app == 'resumes' and operation.source_model == 'ResumeImportJob':
        from resumes.models import ResumeImportJob
        from resumes.tasks import process_resume_import_job
        job = ResumeImportJob.objects.get(pk=operation.source_id, user=operation.user)
        job.status = ResumeImportJob.Status.PENDING
        job.error_message = ''
        job.completed_at = None
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        process_resume_import_job.delay(job.id)
    elif operation.source_app == 'knowledge' and operation.source_model == 'KnowledgeImportBatch':
        from knowledge.models import KnowledgeImportBatch, KnowledgeImportFile
        from knowledge.tasks import process_knowledge_import_file
        batch = KnowledgeImportBatch.objects.get(pk=operation.source_id, uploaded_by=operation.user)
        failed = list(batch.import_files.filter(status=KnowledgeImportFile.Status.FAILED))
        if not failed:
            raise ValueError('no_failed_import_files')
        batch.status = KnowledgeImportBatch.Status.PROCESSING
        batch.save(update_fields=['status', 'updated_at'])
        for item in failed:
            item.status = KnowledgeImportFile.Status.PENDING
            item.error_message = ''
            item.save(update_fields=['status', 'error_message', 'updated_at'])
            process_knowledge_import_file.delay(str(item.id))
    elif operation.source_app == 'video_uploads' and operation.source_model == 'VideoTranscodeTask':
        from video_uploads.models import VideoTranscodeTask
        from video_uploads.tasks import transcode_video_task
        task = VideoTranscodeTask.objects.get(pk=operation.source_id, user=operation.user)
        task.status = VideoTranscodeTask.Status.PENDING
        task.error_message = ''
        task.progress = 0
        task.completed_at = None
        task.save(update_fields=['status', 'error_message', 'progress', 'completed_at'])
        transcode_video_task.delay(str(task.id))
    else:
        raise ValueError('operation_not_retryable')
    operation.status = AsyncOperation.Status.PENDING
    operation.progress = 0
    operation.error_message = ''
    operation.retryable = False
    operation.completed_at = None
    operation.save(update_fields=['status', 'progress', 'error_message', 'retryable', 'completed_at', 'updated_at'])
    return operation
