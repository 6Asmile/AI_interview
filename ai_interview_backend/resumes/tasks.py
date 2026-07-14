import json
import os
from datetime import timedelta

from celery import shared_task
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from knowledge.importers import DocumentParsingService

from .json_resume import imported_text_to_json_resume
from .models import Resume, ResumeImportJob


@shared_task
def mark_stale_resume_import_jobs(timeout_minutes=30):
    threshold = timezone.now() - timedelta(minutes=max(5, int(timeout_minutes)))
    jobs = ResumeImportJob.objects.filter(
        status__in=[ResumeImportJob.Status.PENDING, ResumeImportJob.Status.PROCESSING],
        updated_at__lt=threshold,
    )
    count = 0
    for job in jobs.select_related('resume').iterator():
        previous = job.status
        job.status = ResumeImportJob.Status.FAILED
        job.error_message = f'任务在 {previous} 状态超过 {timeout_minutes} 分钟，请确认 Celery Worker 后重试。'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        job.resume.status = Resume.Status.FAILED
        job.resume.save(update_fields=['status', 'updated_at'])
        count += 1
    return {'failed_jobs': count}


@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def process_resume_import_job(self, job_id: int):
    try:
        job = ResumeImportJob.objects.select_related('resume').get(pk=job_id)
    except ResumeImportJob.DoesNotExist:
        return {'status': 'skipped', 'reason': 'record_deleted', 'job_id': job_id}
    if job.status not in {ResumeImportJob.Status.PENDING, ResumeImportJob.Status.FAILED}:
        return {'status': job.status}
    job.status = ResumeImportJob.Status.PROCESSING
    job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
    resume = job.resume
    resume.status = Resume.Status.PROCESSING
    resume.save(update_fields=['status', 'updated_at'])
    try:
        extension = os.path.splitext(resume.file.name)[1].lower()
        if extension == '.json':
            with open(resume.file.path, 'r', encoding='utf-8-sig') as handle:
                parsed_json = json.load(handle)
            if not isinstance(parsed_json, dict):
                raise ValueError('JSON Resume 根节点必须是对象。')
            from .json_resume import json_resume_plain_text, normalize_json_resume
            parsed_json = normalize_json_resume(parsed_json)
            parsed_text = json_resume_plain_text(parsed_json)
            parser_name = 'json_resume'
            parser_version = parsed_json.get('meta', {}).get('schemaVersion', '1.0.0')
            fallback_reason = ''
        else:
            parser = DocumentParsingService(enable_ocr=True)
            with open(resume.file.path, 'rb') as handle:
                parsed = parser.parse(File(handle, name=resume.file.name.rsplit('/', 1)[-1]))
            parsed_json = imported_text_to_json_resume(resume, parsed.content, parsed.parsed_content)
            parsed_text = parsed.content
            parser_name = parsed.parser_name
            parser_version = parsed.parser_version
            fallback_reason = parsed.parser_fallback_reason
        job.status = ResumeImportJob.Status.REVIEW_REQUIRED
        job.parser_name = parser_name
        job.parser_version = parser_version
        job.parser_fallback_reason = fallback_reason
        job.parsed_text = parsed_text
        job.parsed_json = parsed_json
        job.completed_at = timezone.now()
        job.save(update_fields=[
            'status', 'parser_name', 'parser_version', 'parser_fallback_reason',
            'parsed_text', 'parsed_json', 'completed_at', 'updated_at',
        ])
        resume.parsed_content = parsed_text
        resume.status = Resume.Status.PARSED
        resume.save(update_fields=['parsed_content', 'status', 'updated_at'])
        return {'status': job.status, 'job_id': job.id}
    except Exception as exc:
        job.status = ResumeImportJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        resume.status = Resume.Status.FAILED
        resume.save(update_fields=['status', 'updated_at'])
        return {'status': job.status, 'error': job.error_message}


@transaction.atomic
def confirm_resume_import(job: ResumeImportJob, user, edited_json: dict | None = None):
    from .versioning import create_resume_version
    from .models import ResumeVersion

    locked = ResumeImportJob.objects.select_for_update().select_related('resume').get(pk=job.pk)
    if locked.user_id != user.id:
        raise PermissionError('resume_import_forbidden')
    if locked.status != ResumeImportJob.Status.REVIEW_REQUIRED:
        raise ValueError('resume_import_not_reviewable')
    version = create_resume_version(
        resume=locked.resume,
        resume_json=edited_json or locked.parsed_json,
        layout_json=locked.resume.content_json or {},
        user=user,
        source=ResumeVersion.Source.IMPORT,
        change_summary='确认文件导入结果',
    )
    locked.status = ResumeImportJob.Status.CONFIRMED
    locked.save(update_fields=['status', 'updated_at'])
    return version
