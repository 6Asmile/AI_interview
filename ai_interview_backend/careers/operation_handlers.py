from __future__ import annotations

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import OperationLeaseLost, RetryableOperationError, TerminalOperationError

from .models import JobMatchAnalysis


def _checkpoint(context):
    context.raise_if_canceled()
    if not context.heartbeat():
        raise OperationLeaseLost('career_job_match_lease_lost')


@register_operation_handler('career.job_match')
def handle_job_match(context):
    _checkpoint(context)
    operation = getattr(context, 'operation', None)
    if operation is None:
        operation = context.get_operation()
    if operation.input_type != 'JobMatchAnalysis' or not operation.input_id:
        raise TerminalOperationError('job_match_input_invalid')
    analysis = JobMatchAnalysis.objects.select_related(
        'user', 'job_target', 'resume_version',
    ).filter(
        pk=operation.input_id,
        user=operation.user,
        operation=operation,
    ).first()
    if not analysis:
        raise TerminalOperationError('job_match_analysis_not_found')

    try:
        from .tasks import execute_job_match_analysis

        result = execute_job_match_analysis(analysis, legacy_operation=None)
    except (ConnectionError, TimeoutError) as exc:
        raise RetryableOperationError(
            'job_match_dependency_unavailable',
            str(exc),
            retry_after_seconds=10,
        ) from exc
    except Exception as exc:
        raise TerminalOperationError('job_match_analysis_failed', str(exc)) from exc

    _checkpoint(context)
    analysis.refresh_from_db()
    if analysis.status != JobMatchAnalysis.Status.SUCCEEDED:
        if analysis.status == JobMatchAnalysis.Status.RUNNING:
            raise RetryableOperationError(
                'job_match_still_processing',
                retry_after_seconds=10,
            )
        raise TerminalOperationError(analysis.error_code or 'job_match_analysis_failed')
    return OperationHandlerResult(
        result_type='JobMatchAnalysis',
        result_id=str(analysis.pk),
        result={
            'analysis_id': str(analysis.pk),
            'job_target_id': analysis.job_target_id,
            'status': analysis.status,
            'score': analysis.score,
            'degraded': analysis.degraded,
        },
        metadata={'rule_result_status': result.get('status')},
    )
