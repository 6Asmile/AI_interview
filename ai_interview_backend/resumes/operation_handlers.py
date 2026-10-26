from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import (
    OperationLeaseLost,
    RetryableOperationError,
    TerminalOperationError,
)

from .models import (
    ResumeArtifact,
    ResumeImportJob,
    ResumeOperationRequest,
    ResumeQualityReport,
)


def _checkpoint(context) -> None:
    context.raise_if_canceled()
    if not context.heartbeat():
        raise OperationLeaseLost('resume_operation_lease_lost')


def _load_request(context, operation_type: str) -> ResumeOperationRequest:
    _checkpoint(context)
    operation = getattr(context, 'operation', None)
    if operation is None:
        operation = context.get_operation()
    if operation.input_type != 'ResumeOperationRequest' or not operation.input_id:
        raise TerminalOperationError('resume_operation_input_invalid')
    request_snapshot = ResumeOperationRequest.objects.select_related(
        'resume',
        'artifact',
        'import_job',
        'quality_report',
        'base_version',
        'result_suggestion',
    ).filter(
        pk=operation.input_id,
        user=operation.user,
        operation_type=operation_type,
    ).first()
    if not request_snapshot or request_snapshot.resume.user_id != operation.user_id:
        raise TerminalOperationError('resume_operation_request_not_found')
    return request_snapshot


def _artifact_result(context, operation_type: str) -> OperationHandlerResult:
    request_snapshot = _load_request(context, operation_type)
    artifact = request_snapshot.artifact
    if not artifact or artifact.resume_id != request_snapshot.resume_id:
        raise TerminalOperationError('resume_artifact_not_found')

    from .tasks import render_resume_artifact

    task_result = render_resume_artifact.run(str(artifact.pk), operation_id=None) or {}
    _checkpoint(context)
    artifact.refresh_from_db()
    if artifact.status == ResumeArtifact.Status.READY:
        return OperationHandlerResult(
            result_type='ResumeArtifact',
            result_id=str(artifact.pk),
            result={
                'artifact_id': str(artifact.pk),
                'format': artifact.format,
                'status': artifact.status,
                'reused': bool(task_result.get('reused')),
            },
        )
    error_code = artifact.error_code or 'resume_render_failed'
    message = artifact.error_message or error_code
    if error_code in {'renderer_timeout', 'renderer_unavailable', 'renderer_internal_error'}:
        raise RetryableOperationError(error_code, message, retry_after_seconds=10)
    raise TerminalOperationError(error_code, message)


@register_operation_handler('resume.preview')
def handle_resume_preview(context):
    return _artifact_result(context, 'resume.preview')


@register_operation_handler('resume.export')
def handle_resume_export(context):
    return _artifact_result(context, 'resume.export')


@register_operation_handler('resume.share_export')
def handle_resume_share_export(context):
    return _artifact_result(context, 'resume.share_export')


@register_operation_handler('resume.quality_review')
def handle_resume_quality_review(context):
    request_snapshot = _load_request(context, 'resume.quality_review')
    report = request_snapshot.quality_report
    if not report or report.resume_id != request_snapshot.resume_id:
        raise TerminalOperationError('quality_report_not_found')

    from .tasks import review_resume_quality

    task_result = review_resume_quality.run(report.pk, operation_id=None) or {}
    _checkpoint(context)
    report.refresh_from_db()
    if report.status == ResumeQualityReport.Status.COMPLETED:
        return OperationHandlerResult(
            result_type='ResumeQualityReport',
            result_id=str(report.pk),
            result={
                'quality_report_id': report.pk,
                'status': report.status,
                'score': report.score,
            },
        )
    error_code = str(task_result.get('error_code') or 'quality_review_failed')[:120]
    message = report.error_message or error_code
    if bool(task_result.get('retryable', True)):
        raise RetryableOperationError(error_code, message, retry_after_seconds=5)
    raise TerminalOperationError(error_code, message)


def _handle_resume_import(context, operation_type: str):
    request_snapshot = _load_request(context, operation_type)
    job = request_snapshot.import_job
    if not job or job.resume_id != request_snapshot.resume_id or job.user_id != request_snapshot.user_id:
        raise TerminalOperationError('resume_import_not_found')

    from .tasks import process_resume_import_job

    task_result = process_resume_import_job.run(job.pk, operation_id=None) or {}
    _checkpoint(context)
    job.refresh_from_db()
    if job.status in {ResumeImportJob.Status.REVIEW_REQUIRED, ResumeImportJob.Status.CONFIRMED}:
        return OperationHandlerResult(
            result_type='ResumeImportJob',
            result_id=str(job.pk),
            result={
                'import_job_id': job.pk,
                'resume_id': job.resume_id,
                'status': job.status,
                'review_required': job.status == ResumeImportJob.Status.REVIEW_REQUIRED,
            },
        )
    if job.status == ResumeImportJob.Status.CANCELED:
        raise TerminalOperationError('resume_import_canceled')
    if job.status == ResumeImportJob.Status.PROCESSING:
        raise RetryableOperationError(
            'resume_import_still_processing',
            'Resume import is still processing.',
            retry_after_seconds=30,
        )
    error_code = str(task_result.get('error_code') or 'resume_import_failed')[:120]
    message = job.error_message or error_code
    if bool(task_result.get('retryable', True)):
        raise RetryableOperationError(error_code, message, retry_after_seconds=10)
    raise TerminalOperationError(error_code, message)


@register_operation_handler('resume.import')
def handle_resume_import(context):
    return _handle_resume_import(context, 'resume.import')


@register_operation_handler('resume.import.retry')
def handle_resume_import_retry(context):
    return _handle_resume_import(context, 'resume.import.retry')


@register_operation_handler('resume.suggestion')
def handle_resume_suggestion(context):
    request_snapshot = _load_request(context, 'resume.suggestion')
    if not request_snapshot.base_version_id:
        raise TerminalOperationError('resume_version_not_found')
    if request_snapshot.completed_at:
        return _suggestion_result(request_snapshot, reused=True)

    try:
        from .intelligence import generate_resume_suggestion

        generated = generate_resume_suggestion(
            version=request_snapshot.base_version,
            task_key=request_snapshot.task_key,
            instruction=request_snapshot.instruction,
            job_target_id=request_snapshot.job_target_id,
        )
    except (ConnectionError, TimeoutError) as exc:
        raise RetryableOperationError(
            'resume_suggestion_provider_unavailable',
            str(exc),
            retry_after_seconds=10,
        ) from exc
    except ValueError as exc:
        raise TerminalOperationError(str(exc)[:120] or 'resume_suggestion_invalid', str(exc)) from exc
    except Exception as exc:
        if type(exc).__name__ in {'ModelGatewayError', 'GatewayExecutionError'}:
            raise RetryableOperationError(
                'resume_suggestion_gateway_error',
                str(exc),
                retry_after_seconds=10,
            ) from exc
        raise TerminalOperationError('resume_suggestion_failed', str(exc)) from exc

    suggestion = generated.pop('suggestion')
    stored_result = {
        'questions': generated.get('questions') or [],
        'missing_evidence': generated.get('missing_evidence') or [],
        'prompt_hash': generated.get('prompt_hash') or '',
        'config_hash': generated.get('config_hash') or '',
        'envelope_hash': generated.get('envelope_hash') or '',
        'region_tokens': generated.get('region_tokens') or {},
    }
    with transaction.atomic():
        locked = ResumeOperationRequest.objects.select_for_update().get(pk=request_snapshot.pk)
        if not locked.completed_at:
            locked.result_suggestion = suggestion
            locked.result_json = stored_result
            locked.completed_at = timezone.now()
            locked.save(update_fields=['result_suggestion', 'result_json', 'completed_at'])
        request_snapshot = locked
    _checkpoint(context)
    return _suggestion_result(request_snapshot, reused=False)


def _suggestion_result(request_snapshot: ResumeOperationRequest, *, reused: bool):
    stored = request_snapshot.result_json or {}
    suggestion_id = request_snapshot.result_suggestion_id
    return OperationHandlerResult(
        result_type='ResumeSuggestion',
        result_id=str(suggestion_id or ''),
        result={
            'suggestion_id': suggestion_id,
            'base_version_id': request_snapshot.base_version_id,
            'question_count': len(stored.get('questions') or []),
            'missing_evidence_count': len(stored.get('missing_evidence') or []),
            'prompt_hash': stored.get('prompt_hash') or '',
            'config_hash': stored.get('config_hash') or '',
            'reused': reused,
        },
    )
