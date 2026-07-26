# ai_interview_backend/interviews/tasks.py

import random

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from datetime import timedelta
from knowledge.services import RequiredRAGContextUnavailable
from .execution import cas_transition
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

    claimed = cas_transition(
        execution_id,
        from_statuses=(
            InterviewAgentExecution.Status.ACCEPTED,
            InterviewAgentExecution.Status.ANSWER_PERSISTED,
            InterviewAgentExecution.Status.FAILED_RETRYABLE,
        ),
        to_status=InterviewAgentExecution.Status.EVALUATING,
        started_at=timezone.now(),
        error_code='',
        completed_at=None,
    )
    execution = InterviewAgentExecution.objects.select_related(
        'session__user', 'session__resume', 'trigger_question', 'result_question'
    ).get(id=execution_id)
    if not claimed:
        if execution.status in (
            InterviewAgentExecution.Status.EVALUATING,
            InterviewAgentExecution.Status.EVALUATED,
            InterviewAgentExecution.Status.GENERATING,
            InterviewAgentExecution.Status.COMPLETED,
        ):
            return {'run_id': str(execution.run_id), 'status': execution.status, 'idempotent_replay': True}
        raise RuntimeError(f'execution_not_runnable:{execution.status}')

    session = execution.session
    question = execution.trigger_question
    if not question or not question.answer_text:
        cas_transition(
            execution.id,
            from_statuses=(InterviewAgentExecution.Status.EVALUATING,),
            to_status=InterviewAgentExecution.Status.FAILED_TERMINAL,
            error_code='missing_persisted_answer',
            completed_at=timezone.now(),
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
            last_durable_sequence=1,
            fallback_reason=str(getattr(state, 'fallback_reason', '') or '')[:200],
        ):
            raise RuntimeError('execution_fenced_after_evaluation')
        execution.refresh_from_db()
        publish_agent_event(
            thread_id=session.id,
            run_id=execution.run_id,
            event_type='node.completed',
            sequence=1,
            payload={'node': 'evaluation', 'durable_status': 'evaluated'},
        )
        if state.interview_finished:
            if not cas_transition(
                execution.id,
                from_statuses=(InterviewAgentExecution.Status.EVALUATED,),
                to_status=InterviewAgentExecution.Status.COMPLETED,
                expected_version=execution.version,
                last_durable_sequence=2,
                completed_at=timezone.now(),
            ):
                raise RuntimeError('execution_fenced_before_completion')
            publish_agent_event(
                thread_id=session.id,
                run_id=execution.run_id,
                event_type='run.completed',
                sequence=2,
                payload={'interview_finished': True},
            )
            return {'run_id': str(execution.run_id), 'interview_finished': True}

        job = InterviewQuestionGenerationJob.objects.get(
            session=session,
            answered_question=question,
        )
        with transaction.atomic():
            locked_job = InterviewQuestionGenerationJob.objects.select_for_update().get(id=job.id)
            if locked_job.status == InterviewQuestionGenerationJob.Status.COMPLETED and locked_job.generated_question_id:
                InterviewAgentExecution.objects.filter(id=execution.id).update(
                    status=InterviewAgentExecution.Status.COMPLETED,
                    result_question_id=locked_job.generated_question_id,
                    completed_at=timezone.now(),
                    version=F('version') + 1,
                    updated_at=timezone.now(),
                )
                return {'run_id': str(execution.run_id), 'question_id': locked_job.generated_question_id}
            locked_job.status = InterviewQuestionGenerationJob.Status.RUNNING
            locked_job.started_at = timezone.now()
            locked_job.error_message = ''
            locked_job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
        if not cas_transition(
            execution.id,
            from_statuses=(InterviewAgentExecution.Status.EVALUATED,),
            to_status=InterviewAgentExecution.Status.GENERATING,
            expected_version=execution.version,
        ):
            raise RuntimeError('execution_fenced_before_generation')
        execution.refresh_from_db()
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
            locked_execution.version += 1
            locked_execution.save(update_fields=[
                'status', 'result_question', 'last_durable_sequence', 'completed_at', 'version', 'updated_at',
            ])
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
        return {'run_id': str(execution.run_id), 'question_id': generated.id}
    except Exception as exc:
        if str(exc).startswith('execution_fenced'):
            current_status = InterviewAgentExecution.objects.filter(id=execution.id).values_list('status', flat=True).first()
            return {'run_id': str(execution.run_id), 'status': current_status, 'fenced': True}
        retry_count = InterviewAgentExecution.objects.filter(id=execution.id).values_list('retry_count', flat=True).first() or 0
        retry_count += 1
        terminal = retry_count > self.max_retries
        InterviewAgentExecution.objects.filter(
            id=execution.id,
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
            error_code=type(exc).__name__[:100],
            completed_at=timezone.now() if terminal else None,
            version=F('version') + 1,
            updated_at=timezone.now(),
        )
        InterviewQuestionGenerationJob.objects.filter(
            session=session,
            answered_question=question,
        ).exclude(status=InterviewQuestionGenerationJob.Status.COMPLETED).update(
            status=InterviewQuestionGenerationJob.Status.FAILED,
            error_message=f'{type(exc).__name__}: {str(exc)[:400]}',
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        if isinstance(exc, RequiredRAGContextUnavailable):
            return {
                'run_id': str(execution.run_id),
                'status': InterviewAgentExecution.Status.FAILED_RETRYABLE,
                'paused': True,
                'error_code': 'required_rag_unavailable',
            }
        if terminal:
            raise
        countdown = min(60, (2 ** retry_count) + random.uniform(0, 1.5))
        raise self.retry(exc=exc, countdown=countdown)


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
                dispatch = InterviewAgentDispatch.objects.select_for_update(skip_locked=True).filter(id=dispatch_id).first()
                if not dispatch or dispatch.status == InterviewAgentDispatch.Status.PUBLISHED:
                    continue
                async_result = run_interview_execution.apply_async(
                    args=[str(dispatch.execution_id)],
                    queue='agent',
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
    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    recovered = 0
    candidate_ids = list(
        InterviewAgentExecution.objects.filter(
            status__in=(
                InterviewAgentExecution.Status.ANSWER_PERSISTED,
                InterviewAgentExecution.Status.EVALUATING,
                InterviewAgentExecution.Status.EVALUATED,
                InterviewAgentExecution.Status.GENERATING,
            ),
            updated_at__lt=cutoff,
        ).values_list('id', flat=True)[:200]
    )
    for execution_id in candidate_ids:
        with transaction.atomic():
            execution = InterviewAgentExecution.objects.select_for_update(skip_locked=True).filter(id=execution_id).first()
            if not execution or execution.updated_at >= cutoff:
                continue
            job = InterviewQuestionGenerationJob.objects.filter(
                session=execution.session,
                answered_question_id=execution.trigger_question_id,
            ).select_related('generated_question').first()
            if job and job.status == InterviewQuestionGenerationJob.Status.COMPLETED and job.generated_question_id:
                execution.status = InterviewAgentExecution.Status.COMPLETED
                execution.result_question_id = job.generated_question_id
                execution.completed_at = timezone.now()
                execution.version += 1
                execution.save(update_fields=['status', 'result_question', 'completed_at', 'version', 'updated_at'])
                continue
            execution.status = InterviewAgentExecution.Status.FAILED_RETRYABLE
            execution.retry_count += 1
            execution.error_code = 'stale_execution_recovered'
            execution.version += 1
            execution.save(update_fields=['status', 'retry_count', 'error_code', 'version', 'updated_at'])
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
        publish_pending_agent_dispatches.apply_async(queue='notifications')
    return {'recovered': recovered, 'stale_seconds': stale_seconds}
