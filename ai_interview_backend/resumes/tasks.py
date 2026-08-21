import json
import os
from datetime import timedelta

from celery import shared_task
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from core.models import AsyncOperation
from .json_resume import imported_text_to_json_resume
from .models import Resume, ResumeArtifact, ResumeImportJob, ResumeQualityReport
from .quality import build_multi_perspective_review, build_quality_report
from .rendering import RenderFailure, render_artifact


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
def process_resume_import_job(self, job_id: int, operation_id: str | None = None):
    operation = AsyncOperation.objects.filter(pk=operation_id).first() if operation_id else None
    try:
        job = ResumeImportJob.objects.select_related('resume').get(pk=job_id)
    except ResumeImportJob.DoesNotExist:
        _operation_failed(operation, 'resume_import_not_found', '简历导入任务不存在。')
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
    _operation_running(operation)
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
            from knowledge.importers import DocumentParsingService
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
        if operation:
            operation.status = AsyncOperation.Status.REVIEW_REQUIRED
            operation.progress = 90
            operation.metadata = {
                **(operation.metadata or {}),
                'resume_id': resume.id,
                'import_job_id': job.id,
                'parser_name': parser_name,
            }
            operation.save(update_fields=['status', 'progress', 'metadata', 'updated_at'])
        return {'status': job.status, 'job_id': job.id}
    except Exception as exc:
        job.status = ResumeImportJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        resume.status = Resume.Status.FAILED
        resume.save(update_fields=['status', 'updated_at'])
        retryable = isinstance(exc, (ConnectionError, TimeoutError, RuntimeError))
        _operation_failed(operation, 'resume_import_failed', job.error_message, retryable=retryable)
        return {
            'status': job.status,
            'error': job.error_message,
            'error_code': 'resume_import_failed',
            'exception_type': type(exc).__name__[:120],
            'retryable': retryable,
        }


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
        user=user,
        source=ResumeVersion.Source.IMPORT,
        change_summary='确认文件导入结果',
    )
    locked.status = ResumeImportJob.Status.CONFIRMED
    locked.save(update_fields=['status', 'updated_at'])
    locked.resume.status = Resume.Status.READY
    locked.resume.save(update_fields=['status', 'updated_at'])
    from .studio import ensure_studio
    ensure_studio(locked.resume, user)
    return version


def _operation_running(operation):
    if operation:
        operation.status = AsyncOperation.Status.RUNNING
        operation.progress = 10
        operation.started_at = timezone.now()
        operation.save(update_fields=['status', 'progress', 'started_at', 'updated_at'])


def _operation_succeeded(operation, metadata=None):
    if operation:
        operation.status = AsyncOperation.Status.SUCCEEDED
        operation.progress = 100
        operation.metadata = {**(operation.metadata or {}), **(metadata or {})}
        operation.completed_at = timezone.now()
        operation.save(update_fields=['status', 'progress', 'metadata', 'completed_at', 'updated_at'])


def _operation_failed(operation, code, message, retryable=False):
    if operation:
        operation.status = AsyncOperation.Status.FAILED
        operation.error_code = code
        operation.error_message = message[:2000]
        operation.retryable = retryable
        operation.completed_at = timezone.now()
        operation.save(update_fields=[
            'status', 'error_code', 'error_message', 'retryable', 'completed_at', 'updated_at',
        ])


@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def render_resume_artifact(self, artifact_id: str, operation_id: str | None = None):
    artifact = ResumeArtifact.objects.select_related(
        'resume', 'content_version', 'design_revision',
    ).filter(pk=artifact_id).first()
    operation = AsyncOperation.objects.filter(pk=operation_id).first() if operation_id else None
    if not artifact:
        _operation_failed(operation, 'artifact_not_found', '简历产物不存在。')
        return {'status': 'skipped', 'reason': 'artifact_not_found'}
    if artifact.status == ResumeArtifact.Status.READY:
        _operation_succeeded(operation, {'artifact_id': str(artifact.id), 'reused': True})
        return {'status': artifact.status, 'artifact_id': str(artifact.id), 'reused': True}
    _operation_running(operation)
    try:
        render_artifact(artifact)
        _operation_succeeded(operation, {'artifact_id': str(artifact.id)})
        return {'status': artifact.status, 'artifact_id': str(artifact.id)}
    except RenderFailure as exc:
        artifact.status = ResumeArtifact.Status.FAILED
        artifact.error_code = exc.code
        artifact.error_message = str(exc)[:2000]
        artifact.completed_at = timezone.now()
        artifact.save(update_fields=['status', 'error_code', 'error_message', 'completed_at'])
        retryable = exc.code in {'renderer_timeout', 'renderer_unavailable'}
        _operation_failed(operation, exc.code, str(exc), retryable=retryable)
        return {'status': artifact.status, 'error_code': exc.code, 'retryable': retryable}
    except Exception as exc:
        artifact.status = ResumeArtifact.Status.FAILED
        artifact.error_code = 'renderer_internal_error'
        artifact.error_message = str(exc)[:2000]
        artifact.completed_at = timezone.now()
        artifact.save(update_fields=['status', 'error_code', 'error_message', 'completed_at'])
        _operation_failed(operation, 'renderer_internal_error', str(exc), retryable=True)
        return {'status': artifact.status, 'error_code': artifact.error_code, 'retryable': True}


@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def review_resume_quality(self, report_id: int, operation_id: str | None = None):
    report = ResumeQualityReport.objects.select_related('content_version').filter(pk=report_id).first()
    operation = AsyncOperation.objects.filter(pk=operation_id).first() if operation_id else None
    if not report:
        _operation_failed(operation, 'quality_report_not_found', '简历质量报告不存在。')
        return {'status': 'skipped'}
    if report.status == ResumeQualityReport.Status.COMPLETED:
        _operation_succeeded(operation, {'quality_report_id': report.id, 'reused': True})
        return {'status': report.status, 'quality_report_id': report.id}
    _operation_running(operation)
    report.status = ResumeQualityReport.Status.PROCESSING
    report.save(update_fields=['status'])
    try:
        pointers = set(report.content_version.evidence_links.values_list('json_pointer', flat=True))
        result = build_quality_report(report.content_version.resume_json, pointers)
        try:
            ai_result, ai_metadata = build_multi_perspective_review(report.content_version, result)
            result.update(ai_result)
            result['ai_metadata'] = ai_metadata
            report.config_hash = ai_metadata.get('config_hash') or report.config_hash
        except Exception as ai_exc:
            # Deterministic ATS checks remain useful and must not be hidden by a
            # provider outage. The UI exposes this as a separate degraded layer.
            result.update({
                'ai_review_status': 'unavailable',
                'ai_error_code': type(ai_exc).__name__[:120],
                'reviewers': {},
                'consensus': [],
            })
        report.report_json = result
        report.score = result['score']
        report.status = ResumeQualityReport.Status.COMPLETED
        report.completed_at = timezone.now()
        report.save(update_fields=['report_json', 'score', 'config_hash', 'status', 'completed_at'])
        _operation_succeeded(operation, {'quality_report_id': report.id})
        return {'status': report.status, 'quality_report_id': report.id}
    except Exception as exc:
        report.status = ResumeQualityReport.Status.FAILED
        report.error_message = str(exc)[:2000]
        report.completed_at = timezone.now()
        report.save(update_fields=['status', 'error_message', 'completed_at'])
        retryable = isinstance(exc, (ConnectionError, TimeoutError, RuntimeError))
        _operation_failed(operation, 'quality_review_failed', str(exc), retryable=retryable)
        return {
            'status': report.status,
            'error_code': 'quality_review_failed',
            'exception_type': type(exc).__name__[:120],
            'retryable': retryable,
        }


@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def generate_resume_suggestion_task(
    self,
    version_id: int,
    task_key: str,
    instruction: str,
    job_target_id: int | None,
    operation_id: str,
):
    operation = AsyncOperation.objects.filter(pk=operation_id).first()
    version = ResumeVersion.objects.select_related('resume', 'resume__user').filter(pk=version_id).first()
    if not version:
        _operation_failed(operation, 'resume_version_not_found', '简历版本不存在。')
        return {'status': 'failed', 'error_code': 'resume_version_not_found'}
    _operation_running(operation)
    try:
        from .intelligence import generate_resume_suggestion
        result = generate_resume_suggestion(
            version=version,
            task_key=task_key,
            instruction=instruction,
            job_target_id=job_target_id,
        )
        suggestion = result.pop('suggestion')
        metadata = {
            **result,
            'suggestion_id': suggestion.pk if suggestion else None,
            'base_version_id': version.pk,
        }
        _operation_succeeded(operation, metadata)
        return {'status': 'succeeded', **metadata}
    except Exception as exc:
        _operation_failed(operation, 'resume_suggestion_failed', str(exc), retryable=False)
        return {'status': 'failed', 'error_code': 'resume_suggestion_failed'}
