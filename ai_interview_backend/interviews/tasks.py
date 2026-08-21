# ai_interview_backend/interviews/tasks.py

import random

from celery import shared_task
from core.models import AsyncOperation
from core.operations import (
    OperationLeaseLost,
    checkpoint_operation,
    claim_operation,
    complete_operation,
    fail_operation,
    heartbeat_operation,
    start_operation,
)
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from datetime import timedelta
from knowledge.services import RequiredRAGContextUnavailable
from .execution import cas_transition, claim_execution, heartbeat_execution
from .models import (
    EvaluationRun,
    InterviewAgentDispatch,
    InterviewAgentExecution,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewSession,
)


# @shared_task 装饰器让这个函数成为一个 Celery 任务，
# 并且它不依赖于任何特定的 Celery app 实例，可复用性好。
@shared_task
def cleanup_stale_interviews(apply=False):
    """
    一个定时任务，用于将超过半小时未活动的“进行中”面试标记为“已取消”。
    """
    # 定义超时阈值为半小时前
    timeout_threshold = timezone.now() - timedelta(hours=2)

    # 查找所有状态为 'running' 且最后更新时间在2小时前的面试会话
    # `updated_at__lt` 的意思是 "updated_at less than"
    stale_sessions = InterviewSession.objects.filter(
        status=InterviewSession.Status.RUNNING,
        last_activity_at__lt=timeout_threshold
    )

    stale_ids = list(stale_sessions.values_list('id', flat=True))
    if not apply:
        return {'dry_run': True, 'stale_count': len(stale_ids), 'session_ids': [str(item) for item in stale_ids[:100]]}
    now = timezone.now()
    updated_count = stale_sessions.update(
        status=InterviewSession.Status.CANCELED,
        finished_at=now,
        last_activity_at=now,
    )
    return {'dry_run': False, 'stale_count': len(stale_ids), 'updated_count': updated_count}


@shared_task
def run_evaluation_run(run_id: int):
    from .evaluation import run_offline_rule_evaluation

    run = EvaluationRun.objects.get(id=run_id)
    return run_offline_rule_evaluation(run).summary


@shared_task(bind=True, autoretry_for=(), max_retries=0, acks_late=True)
def run_composite_v4_turn(self, payload: dict):
    """Execute an already-authorized interview turn outside the HTTP process.

    The task reloads every business object from PostgreSQL and validates the
    owner again. It never trusts ORM-shaped data supplied by the Agent service.
    """

    import json
    from django.db import transaction

    from .agent_v4.contracts import AgentEvent, AgentTurnInput
    from .agent_v4.engine import CompositeV4InterviewAgentEngine
    from .agent_v4.events import publish_agent_event
    from .models import InterviewQuestion

    turn = AgentTurnInput.model_validate_json(json.dumps(payload, ensure_ascii=False))
    if turn.event != AgentEvent.SUBMIT_ANSWER:
        raise ValueError('unsupported_agent_event')
    with transaction.atomic():
        session = InterviewSession.objects.select_for_update().select_related('user', 'resume').get(
            id=turn.session_id,
            user_id=turn.user_id,
            status=InterviewSession.Status.RUNNING,
        )
        question = InterviewQuestion.objects.select_for_update().get(id=turn.question_id, session=session)
        if question.answer_text and question.answer_text != turn.answer_text:
            raise ValueError('answer_conflicts_with_persisted_turn')
        if not question.answer_text:
            question.answer_text = turn.answer_text
            question.answered_at = timezone.now()
            question.save(update_fields=['answer_text', 'answered_at'])

    history = [
        {
            'sequence': item.sequence,
            'question': item.question_text,
            'answer': item.answer_text,
            'evaluation': item.ai_feedback if isinstance(item.ai_feedback, dict) else {},
            'rag_context': item.rag_context if isinstance(item.rag_context, list) else [],
        }
        for item in session.questions.filter(answered_at__isnull=False).order_by('sequence')
    ]
    engine = CompositeV4InterviewAgentEngine()
    state = engine.prepare_submit_answer_turn(
        session=session,
        current_question=question,
        answer_text=turn.answer_text,
        user=session.user,
        answered_count=turn.answered_count,
        history=history,
        resume_text=turn.resume_text,
        jd_text=turn.jd_text,
        media_context=turn.media_context,
    )
    sequence = 0
    publish_agent_event(
        thread_id=session.id,
        run_id=state.agent_run_id,
        event_type='run.started',
        sequence=sequence,
        payload={'celery_task_id': self.request.id},
    )
    if state.interview_finished:
        publish_agent_event(
            thread_id=session.id,
            run_id=state.agent_run_id,
            event_type='run.completed',
            sequence=1,
            payload={'interview_finished': True},
        )
        return {'run_id': str(state.agent_run_id), 'interview_finished': True}

    chunks = []
    for chunk in engine.generate_question_chunks(state):
        chunks.append(chunk)
        sequence += 1
        publish_agent_event(
            thread_id=session.id,
            run_id=state.agent_run_id,
            event_type='question.delta',
            sequence=sequence,
            payload={'delta': chunk},
        )
    generated = engine.finalize_generated_question(state, ''.join(chunks))
    sequence += 1
    publish_agent_event(
        thread_id=session.id,
        run_id=state.agent_run_id,
        event_type='question.completed',
        sequence=sequence,
        payload={
            'question': {
                'id': generated.id,
                'sequence': generated.sequence,
                'question_text': generated.question_text,
            },
        },
    )
    return {'run_id': str(state.agent_run_id), 'question_id': generated.id}


def _resume_text(session: InterviewSession) -> str:
    if session.resume_snapshot:
        try:
            from resumes.json_resume import json_resume_plain_text
            return json_resume_plain_text(session.resume_snapshot)
        except Exception:
            pass
    if session.resume:
        return session.resume.parsed_content or session.resume.summary or ''
    return ''


class _AgentProjectionClaimConflict(RuntimeError):
    """Force the outer transaction to roll back a half-acquired projection."""


def _claim_agent_projection(execution_id, *, lease_owner: str):
    """Claim the Agent execution and its public Operation under one DB transaction."""

    with transaction.atomic():
        execution_ref = InterviewAgentExecution.objects.select_for_update().select_related('operation').get(
            id=execution_id,
        )
        operation_claim = None
        operation_status = ''
        if execution_ref.operation_id:
            operation_claim = claim_operation(
                execution_ref.operation_id,
                worker_id=lease_owner,
                lease_seconds=getattr(settings, 'AGENT_EXECUTION_LEASE_SECONDS', 360),
            )
            operation_status = AsyncOperation.objects.only('status').get(
                id=execution_ref.operation_id,
            ).status
            if operation_claim is None:
                if operation_status == AsyncOperation.Status.CANCELED:
                    InterviewAgentExecution.objects.filter(id=execution_id).exclude(
                        status=InterviewAgentExecution.Status.COMPLETED,
                    ).update(
                        status=InterviewAgentExecution.Status.CANCELED,
                        lease_owner='',
                        lease_expires_at=None,
                        heartbeat_at=timezone.now(),
                        completed_at=timezone.now(),
                        version=F('version') + 1,
                        updated_at=timezone.now(),
                    )
                    InterviewAgentDispatch.objects.filter(execution_id=execution_id).update(
                        status=InterviewAgentDispatch.Status.CANCELED,
                        updated_at=timezone.now(),
                    )
                return None, None, operation_status

        execution = claim_execution(
            execution_id,
            lease_owner=lease_owner,
            from_statuses=(
                InterviewAgentExecution.Status.ACCEPTED,
                InterviewAgentExecution.Status.ANSWER_PERSISTED,
                InterviewAgentExecution.Status.FAILED_RETRYABLE,
            ),
            to_status=InterviewAgentExecution.Status.EVALUATING,
        )
        if execution is None:
            # Raising is deliberate: if the Operation was claimed immediately
            # before the domain CAS failed, both changes must roll back.
            raise _AgentProjectionClaimConflict('agent_execution_not_claimable')
        if operation_claim:
            start_operation(operation_claim)
        return execution, operation_claim, operation_status


def _heartbeat_agent_projection(execution, *, lease_owner: str, operation_claim) -> bool:
    try:
        with transaction.atomic():
            if operation_claim and not heartbeat_operation(
                operation_claim,
                lease_seconds=getattr(settings, 'AGENT_EXECUTION_LEASE_SECONDS', 360),
            ):
                raise OperationLeaseLost('operation_fenced_during_agent_heartbeat')
            if not heartbeat_execution(
                execution.id,
                lease_owner=lease_owner,
                fencing_token=execution.fencing_token,
            ):
                raise OperationLeaseLost('execution_fenced_during_agent_heartbeat')
        return True
    except OperationLeaseLost:
        return False


def _retryable_agent_error(exc: Exception) -> bool:
    if isinstance(exc, (RequiredRAGContextUnavailable, ConnectionError, TimeoutError)):
        return True
    marker = f'{type(exc).__name__}:{exc}'.lower()
    return any(value in marker for value in (
        'timeout', 'timed out', 'connection', 'temporar', 'rate limit', 'ratelimit', '429',
        '502', '503', '504',
    ))


@shared_task(
    bind=True,
    max_retries=4,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=300,
)
def run_interview_execution(self, execution_id: str):
    """Resume a durable Agent execution without holding locks during model calls."""

    lease_owner = str(self.request.id or f'celery:{execution_id}')[:128]
    try:
        execution, operation_claim, operation_status = _claim_agent_projection(
            execution_id,
            lease_owner=lease_owner,
        )
    except _AgentProjectionClaimConflict:
        execution = None
        operation_claim = None
        operation_status = ''
    if execution is None:
        execution = InterviewAgentExecution.objects.select_related(
            'session__user', 'session__resume', 'trigger_question', 'result_question', 'operation'
        ).get(id=execution_id)
        if execution.status in (
            InterviewAgentExecution.Status.EVALUATING,
            InterviewAgentExecution.Status.EVALUATED,
            InterviewAgentExecution.Status.GENERATING,
            InterviewAgentExecution.Status.COMPLETED,
            InterviewAgentExecution.Status.CANCELED,
        ):
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'status': execution.status,
                'idempotent_replay': True,
            }
        if operation_status in (
            AsyncOperation.Status.CLAIMED,
            AsyncOperation.Status.RUNNING,
            AsyncOperation.Status.SUCCEEDED,
            AsyncOperation.Status.FAILED,
            AsyncOperation.Status.CANCELED,
        ):
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'status': operation_status,
                'idempotent_replay': True,
            }
        raise RuntimeError(f'execution_not_runnable:{execution.status}')
    execution = InterviewAgentExecution.objects.select_related(
        'session__user', 'session__resume', 'trigger_question', 'result_question', 'operation'
    ).get(id=execution_id)
    fencing_token = execution.fencing_token

    session = execution.session
    question = execution.trigger_question
    if not question or not question.answer_text:
        with transaction.atomic():
            if not cas_transition(
                execution.id,
                from_statuses=(InterviewAgentExecution.Status.EVALUATING,),
                to_status=InterviewAgentExecution.Status.FAILED_TERMINAL,
                expected_version=execution.version,
                lease_owner=lease_owner,
                fencing_token=fencing_token,
                release_lease=True,
                error_code='missing_persisted_answer',
                completed_at=timezone.now(),
            ):
                raise RuntimeError('execution_fenced_before_missing_answer_failure')
            if operation_claim:
                fail_operation(
                    operation_claim,
                    error_code='missing_persisted_answer',
                    error_message='Persisted answer is unavailable.',
                    retryable=False,
                    dispatch_retry=False,
                )
        raise ValueError('missing_persisted_answer')

    try:
        history = [
            {
                'sequence': item.sequence,
                'question': item.question_text,
                'answer': item.answer_text,
                'evaluation': item.ai_feedback if isinstance(item.ai_feedback, dict) else {},
                'rag_context': item.rag_context if isinstance(item.rag_context, list) else [],
            }
            for item in session.questions.filter(answered_at__isnull=False).order_by('sequence')
        ]
        from .agent import get_interview_agent_engine
        from .agent_v4.events import publish_agent_event

        engine = get_interview_agent_engine()
        state = engine.prepare_submit_answer_turn(
            session=session,
            current_question=question,
            answer_text=question.answer_text,
            user=session.user,
            answered_count=len(history),
            history=history,
            resume_text=_resume_text(session),
            jd_text=session.jd_snapshot or (session.memory_summary or {}).get('jd_text', ''),
            media_context=(execution.state_metadata or {}).get('media_context', {}),
        )
        if not cas_transition(
            execution.id,
            from_statuses=(InterviewAgentExecution.Status.EVALUATING, InterviewAgentExecution.Status.EVALUATED),
            to_status=InterviewAgentExecution.Status.EVALUATED,
            expected_version=execution.version,
            lease_owner=lease_owner,
            fencing_token=fencing_token,
            last_durable_sequence=1,
            fallback_reason=str(getattr(state, 'fallback_reason', '') or '')[:200],
        ):
            raise RuntimeError('execution_fenced_after_evaluation')
        execution.refresh_from_db()
        if operation_claim:
            checkpoint_operation(
                operation_claim,
                progress=45,
                event_type='interview.answer_evaluated',
                payload={'execution_id': str(execution.id)},
                lease_seconds=getattr(settings, 'AGENT_EXECUTION_LEASE_SECONDS', 360),
            )
        publish_agent_event(
            thread_id=session.id,
            run_id=execution.run_id,
            event_type='node.completed',
            sequence=1,
            payload={'node': 'evaluation', 'durable_status': 'evaluated'},
        )
        if state.interview_finished:
            with transaction.atomic():
                if not cas_transition(
                    execution.id,
                    from_statuses=(InterviewAgentExecution.Status.EVALUATED,),
                    to_status=InterviewAgentExecution.Status.COMPLETED,
                    expected_version=execution.version,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                    release_lease=True,
                    last_durable_sequence=2,
                    completed_at=timezone.now(),
                ):
                    raise RuntimeError('execution_fenced_before_completion')
                if operation_claim:
                    complete_operation(
                        operation_claim,
                        result_type='InterviewSession',
                        result_id=str(session.id),
                        result={
                            'interview_finished': True,
                            'agent_run_id': str(execution.run_id),
                        },
                    )
            publish_agent_event(
                thread_id=session.id,
                run_id=execution.run_id,
                event_type='run.completed',
                sequence=2,
                payload={'interview_finished': True},
            )
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'interview_finished': True,
            }

        job = InterviewQuestionGenerationJob.objects.get(
            session=session,
            answered_question=question,
        )
        with transaction.atomic():
            locked_job = InterviewQuestionGenerationJob.objects.select_for_update().get(id=job.id)
            if locked_job.status == InterviewQuestionGenerationJob.Status.COMPLETED and locked_job.generated_question_id:
                updated = InterviewAgentExecution.objects.filter(
                    id=execution.id,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                ).update(
                    status=InterviewAgentExecution.Status.COMPLETED,
                    result_question_id=locked_job.generated_question_id,
                    completed_at=timezone.now(),
                    lease_owner='',
                    lease_expires_at=None,
                    heartbeat_at=timezone.now(),
                    version=F('version') + 1,
                    updated_at=timezone.now(),
                )
                if not updated:
                    raise RuntimeError('execution_fenced_before_reusing_result')
                if operation_claim:
                    complete_operation(
                        operation_claim,
                        result_type='InterviewQuestion',
                        result_id=str(locked_job.generated_question_id),
                        result={
                            'question_id': locked_job.generated_question_id,
                            'agent_run_id': str(execution.run_id),
                            'reused': True,
                        },
                    )
                return {
                    'operation_id': str(execution.operation_id) if execution.operation_id else None,
                    'run_id': str(execution.run_id),
                    'question_id': locked_job.generated_question_id,
                }
            locked_job.status = InterviewQuestionGenerationJob.Status.RUNNING
            locked_job.started_at = timezone.now()
            locked_job.error_message = ''
            locked_job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
        if not cas_transition(
            execution.id,
            from_statuses=(InterviewAgentExecution.Status.EVALUATED,),
            to_status=InterviewAgentExecution.Status.GENERATING,
            expected_version=execution.version,
            lease_owner=lease_owner,
            fencing_token=fencing_token,
        ):
            raise RuntimeError('execution_fenced_before_generation')
        execution.refresh_from_db()
        if operation_claim:
            checkpoint_operation(
                operation_claim,
                progress=60,
                event_type='interview.question_generation_started',
                payload={'execution_id': str(execution.id)},
                lease_seconds=getattr(settings, 'AGENT_EXECUTION_LEASE_SECONDS', 360),
            )
        if hasattr(state, 'v2_state') and isinstance(state.v2_state, dict):
            state.v2_state['execution_version'] = execution.version

        chunks = []
        event_sequence = 1
        last_checkpoint_length = 0
        for chunk in engine.generate_question_chunks(state):
            chunks.append(chunk)
            event_sequence += 1
            text = ''.join(chunks)
            if len(text) - last_checkpoint_length >= 512:
                InterviewQuestionGenerationJob.objects.filter(id=job.id).update(
                    partial_text=text,
                    updated_at=timezone.now(),
                )
                if not _heartbeat_agent_projection(
                    execution,
                    lease_owner=lease_owner,
                    operation_claim=operation_claim,
                ):
                    raise RuntimeError('execution_fenced_during_generation')
                last_checkpoint_length = len(text)
            publish_agent_event(
                thread_id=session.id,
                run_id=execution.run_id,
                event_type='question.delta',
                sequence=event_sequence,
                payload={'delta': chunk},
            )
        generated = engine.finalize_generated_question(state, ''.join(chunks))
        event_sequence += 1
        with transaction.atomic():
            locked_execution = InterviewAgentExecution.objects.select_for_update().filter(
                id=execution.id,
                status__in=(InterviewAgentExecution.Status.GENERATING, InterviewAgentExecution.Status.COMPLETED),
                version=execution.version,
                lease_owner=lease_owner,
                fencing_token=fencing_token,
            ).first()
            if not locked_execution:
                raise RuntimeError('execution_fenced_before_persist')
            InterviewQuestionGenerationJob.objects.filter(id=job.id).update(
                generated_question=generated,
                final_text=generated.question_text,
                partial_text=''.join(chunks),
                status=InterviewQuestionGenerationJob.Status.COMPLETED,
                completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            locked_execution.status = InterviewAgentExecution.Status.COMPLETED
            locked_execution.result_question = generated
            locked_execution.last_durable_sequence = event_sequence
            locked_execution.completed_at = timezone.now()
            locked_execution.lease_owner = ''
            locked_execution.lease_expires_at = None
            locked_execution.heartbeat_at = timezone.now()
            locked_execution.version += 1
            locked_execution.save(update_fields=[
                'status', 'result_question', 'last_durable_sequence', 'completed_at',
                'lease_owner', 'lease_expires_at', 'heartbeat_at', 'version', 'updated_at',
            ])
            if operation_claim:
                complete_operation(
                    operation_claim,
                    result_type='InterviewQuestion',
                    result_id=str(generated.id),
                    result={
                        'question_id': generated.id,
                        'sequence': generated.sequence,
                        'agent_run_id': str(execution.run_id),
                    },
                )
        publish_agent_event(
            thread_id=session.id,
            run_id=execution.run_id,
            event_type='question.completed',
            sequence=event_sequence,
            payload={'question': {
                'id': generated.id,
                'sequence': generated.sequence,
                'question_text': generated.question_text,
            }},
        )
        return {
            'operation_id': str(execution.operation_id) if execution.operation_id else None,
            'run_id': str(execution.run_id),
            'question_id': generated.id,
        }
    except Exception as exc:
        if isinstance(exc, OperationLeaseLost) or str(exc).startswith(('execution_fenced', 'operation_fenced')):
            current_status = InterviewAgentExecution.objects.filter(id=execution.id).values_list('status', flat=True).first()
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'status': current_status,
                'fenced': True,
            }
        retry_count = InterviewAgentExecution.objects.filter(id=execution.id).values_list('retry_count', flat=True).first() or 0
        retry_count += 1
        retryable = _retryable_agent_error(exc)
        terminal = not retryable or retry_count > self.max_retries
        countdown = min(60, (2 ** retry_count) + random.uniform(0, 1.5))
        error_code = (
            'required_rag_unavailable'
            if isinstance(exc, RequiredRAGContextUnavailable)
            else type(exc).__name__[:100]
        )
        try:
            with transaction.atomic():
                updated = InterviewAgentExecution.objects.filter(
                    id=execution.id,
                    lease_owner=lease_owner,
                    fencing_token=fencing_token,
                    status__in=(
                        InterviewAgentExecution.Status.EVALUATING,
                        InterviewAgentExecution.Status.EVALUATED,
                        InterviewAgentExecution.Status.GENERATING,
                    ),
                ).update(
                    status=(
                        InterviewAgentExecution.Status.FAILED_TERMINAL
                        if terminal else InterviewAgentExecution.Status.FAILED_RETRYABLE
                    ),
                    retry_count=retry_count,
                    error_code=error_code,
                    completed_at=timezone.now() if terminal else None,
                    lease_owner='',
                    lease_expires_at=None,
                    heartbeat_at=timezone.now(),
                    version=F('version') + 1,
                    updated_at=timezone.now(),
                )
                if not updated:
                    raise OperationLeaseLost('execution_fenced_while_recording_failure')
                if operation_claim:
                    fail_operation(
                        operation_claim,
                        error_code=error_code,
                        error_message='The interview Agent could not complete this attempt.',
                        retryable=not terminal,
                        retry_after_seconds=countdown,
                        dispatch_retry=False,
                    )
                generation_status = (
                    InterviewQuestionGenerationJob.Status.FAILED
                    if terminal else InterviewQuestionGenerationJob.Status.PENDING
                )
                InterviewQuestionGenerationJob.objects.filter(
                    session=session,
                    answered_question=question,
                ).exclude(status=InterviewQuestionGenerationJob.Status.COMPLETED).update(
                    status=generation_status,
                    error_message=f'{error_code}: agent execution failed',
                    started_at=None if not terminal else F('started_at'),
                    completed_at=timezone.now() if terminal else None,
                    updated_at=timezone.now(),
                )
                if not terminal:
                    InterviewAgentDispatch.objects.filter(execution=execution).update(
                        status=InterviewAgentDispatch.Status.FAILED,
                        error_code=error_code,
                        error_message='Database-scheduled Agent retry.',
                        next_attempt_at=timezone.now() + timedelta(seconds=countdown),
                        updated_at=timezone.now(),
                    )
        except OperationLeaseLost:
            current_status = InterviewAgentExecution.objects.filter(id=execution.id).values_list('status', flat=True).first()
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'status': current_status,
                'fenced': True,
            }
        if isinstance(exc, RequiredRAGContextUnavailable):
            return {
                'operation_id': str(execution.operation_id) if execution.operation_id else None,
                'run_id': str(execution.run_id),
                'status': InterviewAgentExecution.Status.FAILED_RETRYABLE,
                'paused': True,
                'error_code': 'required_rag_unavailable',
                'retry_after_ms': int(countdown * 1000),
            }
        if terminal:
            raise
        return {
            'operation_id': str(execution.operation_id) if execution.operation_id else None,
            'run_id': str(execution.run_id),
            'status': InterviewAgentExecution.Status.FAILED_RETRYABLE,
            'retry_scheduled': True,
            'retry_after_ms': int(countdown * 1000),
        }


@shared_task(bind=True, acks_late=True, soft_time_limit=30, time_limit=45)
def publish_pending_agent_dispatches(self, batch_size=100):
    """Publish transactional Agent outbox rows; duplicate deliveries are harmless."""

    now = timezone.now()
    published = 0
    failed = 0
    ids = list(
        InterviewAgentDispatch.objects.filter(
            Q(status=InterviewAgentDispatch.Status.PENDING)
            | Q(status=InterviewAgentDispatch.Status.FAILED, next_attempt_at__lte=now)
        ).order_by('created_at').values_list('id', flat=True)[:batch_size]
    )
    for dispatch_id in ids:
        try:
            with transaction.atomic():
                dispatch = InterviewAgentDispatch.objects.select_for_update(skip_locked=True).select_related(
                    'execution__operation',
                ).filter(id=dispatch_id).first()
                if not dispatch or dispatch.status == InterviewAgentDispatch.Status.PUBLISHED:
                    continue
                operation = dispatch.execution.operation
                if operation and operation.status in (
                    AsyncOperation.Status.CANCEL_REQUESTED,
                    AsyncOperation.Status.CANCELED,
                    AsyncOperation.Status.SUCCEEDED,
                    AsyncOperation.Status.FAILED,
                ):
                    dispatch.status = InterviewAgentDispatch.Status.CANCELED
                    dispatch.error_code = 'operation_not_dispatchable'
                    dispatch.error_message = ''
                    dispatch.next_attempt_at = None
                    dispatch.save(update_fields=[
                        'status', 'error_code', 'error_message', 'next_attempt_at', 'updated_at',
                    ])
                    continue
                if operation and operation.next_attempt_at and operation.next_attempt_at > now:
                    dispatch.next_attempt_at = operation.next_attempt_at
                    dispatch.save(update_fields=['next_attempt_at', 'updated_at'])
                    continue
                async_result = run_interview_execution.apply_async(
                    args=[str(dispatch.execution_id)],
                    queue=getattr(settings, 'CELERY_AGENT_QUEUE', 'ifaceoff.v2.agent.interactive'),
                    mandatory=True,
                )
                dispatch.status = InterviewAgentDispatch.Status.PUBLISHED
                dispatch.celery_task_id = async_result.id or ''
                dispatch.attempts += 1
                dispatch.error_code = ''
                dispatch.error_message = ''
                dispatch.published_at = timezone.now()
                dispatch.save(update_fields=[
                    'status', 'celery_task_id', 'attempts', 'error_code', 'error_message',
                    'published_at', 'updated_at',
                ])
                published += 1
        except Exception as exc:
            failed += 1
            InterviewAgentDispatch.objects.filter(id=dispatch_id).update(
                status=InterviewAgentDispatch.Status.FAILED,
                attempts=F('attempts') + 1,
                error_code=type(exc).__name__[:120],
                error_message=str(exc)[:1000],
                next_attempt_at=timezone.now() + timedelta(seconds=10),
                updated_at=timezone.now(),
            )
    return {'published': published, 'failed': failed}


@shared_task(acks_late=True)
def recover_stale_agent_executions():
    """Fence stale workers and make their durable executions dispatchable again."""

    stale_seconds = int(getattr(settings, 'AGENT_EXECUTION_STALE_SECONDS', 360))
    now = timezone.now()
    cutoff = now - timedelta(seconds=stale_seconds)
    recovered = 0
    candidate_ids = list(
        InterviewAgentExecution.objects.filter(
            status__in=(
                InterviewAgentExecution.Status.ANSWER_PERSISTED,
                InterviewAgentExecution.Status.EVALUATING,
                InterviewAgentExecution.Status.EVALUATED,
                InterviewAgentExecution.Status.GENERATING,
            ),
        ).filter(
            Q(lease_expires_at__lte=now)
            | Q(lease_expires_at__isnull=True, updated_at__lt=cutoff),
        ).values_list('id', flat=True)[:200]
    )
    for execution_id in candidate_ids:
        with transaction.atomic():
            execution = InterviewAgentExecution.objects.select_for_update(skip_locked=True).select_related(
                'operation',
            ).filter(id=execution_id).first()
            if not execution:
                continue
            lease_is_stale = bool(execution.lease_expires_at and execution.lease_expires_at <= now)
            never_claimed_is_stale = execution.lease_expires_at is None and execution.updated_at < cutoff
            if not (lease_is_stale or never_claimed_is_stale):
                continue
            recovery_claim = None
            operation_status = ''
            if execution.operation_id:
                recovery_claim = claim_operation(
                    execution.operation_id,
                    worker_id=f'agent-recovery:{execution.id}'[:160],
                    lease_seconds=getattr(settings, 'AGENT_EXECUTION_LEASE_SECONDS', 360),
                )
                operation_status = AsyncOperation.objects.only('status').get(
                    id=execution.operation_id,
                ).status
                if recovery_claim is None:
                    if operation_status == AsyncOperation.Status.CANCELED:
                        execution.status = InterviewAgentExecution.Status.CANCELED
                        execution.completed_at = timezone.now()
                        execution.fencing_token += 1
                        execution.lease_owner = ''
                        execution.lease_expires_at = None
                        execution.heartbeat_at = timezone.now()
                        execution.version += 1
                        execution.save(update_fields=[
                            'status', 'completed_at', 'fencing_token', 'lease_owner',
                            'lease_expires_at', 'heartbeat_at', 'version', 'updated_at',
                        ])
                        InterviewAgentDispatch.objects.filter(execution=execution).update(
                            status=InterviewAgentDispatch.Status.CANCELED,
                            updated_at=timezone.now(),
                        )
                    elif operation_status == AsyncOperation.Status.FAILED:
                        execution.status = InterviewAgentExecution.Status.FAILED_TERMINAL
                        execution.completed_at = timezone.now()
                        execution.error_code = 'operation_attempts_exhausted'
                        execution.fencing_token += 1
                        execution.lease_owner = ''
                        execution.lease_expires_at = None
                        execution.heartbeat_at = timezone.now()
                        execution.version += 1
                        execution.save(update_fields=[
                            'status', 'completed_at', 'error_code', 'fencing_token', 'lease_owner',
                            'lease_expires_at', 'heartbeat_at', 'version', 'updated_at',
                        ])
                    elif operation_status == AsyncOperation.Status.SUCCEEDED:
                        completed_job = InterviewQuestionGenerationJob.objects.filter(
                            session=execution.session,
                            answered_question_id=execution.trigger_question_id,
                            status=InterviewQuestionGenerationJob.Status.COMPLETED,
                            generated_question__isnull=False,
                        ).first()
                        execution.status = InterviewAgentExecution.Status.COMPLETED
                        execution.result_question_id = (
                            completed_job.generated_question_id if completed_job else execution.result_question_id
                        )
                        execution.completed_at = timezone.now()
                        execution.fencing_token += 1
                        execution.lease_owner = ''
                        execution.lease_expires_at = None
                        execution.heartbeat_at = timezone.now()
                        execution.version += 1
                        execution.save(update_fields=[
                            'status', 'result_question', 'completed_at', 'fencing_token', 'lease_owner',
                            'lease_expires_at', 'heartbeat_at', 'version', 'updated_at',
                        ])
                    continue
                start_operation(recovery_claim)
            job = InterviewQuestionGenerationJob.objects.filter(
                session=execution.session,
                answered_question_id=execution.trigger_question_id,
            ).select_related('generated_question').first()
            if job and job.status == InterviewQuestionGenerationJob.Status.COMPLETED and job.generated_question_id:
                execution.status = InterviewAgentExecution.Status.COMPLETED
                execution.result_question_id = job.generated_question_id
                execution.completed_at = timezone.now()
                execution.version += 1
                execution.fencing_token += 1
                execution.lease_owner = ''
                execution.lease_expires_at = None
                execution.heartbeat_at = timezone.now()
                execution.save(update_fields=[
                    'status', 'result_question', 'completed_at', 'version', 'fencing_token',
                    'lease_owner', 'lease_expires_at', 'heartbeat_at', 'updated_at',
                ])
                if recovery_claim:
                    complete_operation(
                        recovery_claim,
                        result_type='InterviewQuestion',
                        result_id=str(job.generated_question_id),
                        result={
                            'question_id': job.generated_question_id,
                            'agent_run_id': str(execution.run_id),
                            'recovered': True,
                        },
                    )
                continue
            execution.status = InterviewAgentExecution.Status.FAILED_RETRYABLE
            execution.retry_count += 1
            execution.error_code = 'stale_execution_recovered'
            execution.version += 1
            execution.fencing_token += 1
            execution.lease_owner = ''
            execution.lease_expires_at = None
            execution.heartbeat_at = timezone.now()
            execution.save(update_fields=[
                'status', 'retry_count', 'error_code', 'version', 'fencing_token',
                'lease_owner', 'lease_expires_at', 'heartbeat_at', 'updated_at',
            ])
            if recovery_claim:
                fail_operation(
                    recovery_claim,
                    error_code='stale_execution_recovered',
                    error_message='A stale Agent lease was recovered.',
                    retryable=True,
                    retry_after_seconds=0,
                    dispatch_retry=False,
                )
            dispatch, _ = InterviewAgentDispatch.objects.get_or_create(execution=execution)
            dispatch.status = InterviewAgentDispatch.Status.PENDING
            dispatch.next_attempt_at = None
            dispatch.error_code = ''
            dispatch.error_message = ''
            dispatch.save(update_fields=['status', 'next_attempt_at', 'error_code', 'error_message', 'updated_at'])
            if job and job.status != InterviewQuestionGenerationJob.Status.COMPLETED:
                job.status = InterviewQuestionGenerationJob.Status.PENDING
                job.error_message = ''
                job.started_at = None
                job.completed_at = None
                job.save(update_fields=['status', 'error_message', 'started_at', 'completed_at', 'updated_at'])
            recovered += 1
    if recovered:
        publish_pending_agent_dispatches.apply_async(
            queue=getattr(settings, 'CELERY_PUBLISHER_QUEUE', 'ifaceoff.v2.publisher'),
            mandatory=True,
        )
    return {'recovered': recovered, 'stale_seconds': stale_seconds}
