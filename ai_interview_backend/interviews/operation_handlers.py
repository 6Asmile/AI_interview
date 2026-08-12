from __future__ import annotations

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import RetryableOperationError, TerminalOperationError

from .models import EvaluationRun


@register_operation_handler('interview.evaluation')
def run_interview_evaluation_operation(context):
    operation = context.get_operation()
    try:
        run = EvaluationRun.objects.select_related('created_by', 'dataset', 'template').get(
            id=operation.input_id,
            created_by=operation.user,
        )
    except EvaluationRun.DoesNotExist as exc:
        raise TerminalOperationError('evaluation_run_not_found') from exc

    context.raise_if_canceled()
    if run.status == EvaluationRun.Status.SUCCEEDED:
        return OperationHandlerResult(
            result_type='EvaluationRun',
            result_id=str(run.id),
            result={'evaluation_run_id': run.id, 'summary': run.summary, 'reused': True},
        )

    # A prior worker may have crashed midway through metric persistence. The
    # durable Operation fence serializes execution; clearing partial metrics
    # makes the domain result idempotent on a later leased retry.
    run.metrics.all().delete()
    run.status = EvaluationRun.Status.PENDING
    run.error_message = ''
    run.started_at = None
    run.finished_at = None
    run.save(update_fields=['status', 'error_message', 'started_at', 'finished_at'])
    context.heartbeat()
    try:
        from .evaluation import run_offline_rule_evaluation

        run_offline_rule_evaluation(run)
    except (ConnectionError, TimeoutError) as exc:
        raise RetryableOperationError(
            'evaluation_dependency_unavailable',
            retry_after_seconds=30,
        ) from exc
    except (ValueError, TypeError) as exc:
        raise TerminalOperationError('evaluation_input_invalid') from exc

    context.raise_if_canceled()
    return OperationHandlerResult(
        result_type='EvaluationRun',
        result_id=str(run.id),
        result={'evaluation_run_id': run.id, 'summary': run.summary},
    )
