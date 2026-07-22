from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Iterable

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from .agent import get_interview_agent_engine
from .models import (
    InterviewAgentDispatch,
    InterviewAgentExecution,
    InterviewAgentRun,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewSession,
)


@contextmanager
def short_lock_timeout(milliseconds: int | None = None):
    """Bound PostgreSQL user-facing lock waits to a short, retryable window."""

    timeout = int(milliseconds or getattr(settings, 'INTERVIEW_LOCK_TIMEOUT_MS', 1500))
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL lock_timeout = %s', [f'{timeout}ms'])
    yield


def _fallback_request_hash(session, question, answer_text: str, event: str) -> str:
    raw = json.dumps({
        'session_id': str(session.id),
        'question_id': question.id,
        'answer_text': answer_text,
        'answered_at': question.answered_at.isoformat() if question.answered_at else '',
        'event': event,
        'state_schema_version': 4,
    }, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def agent_request_hash(session, question, answer_text: str, event='submit_answer_stream') -> str:
    engine = get_interview_agent_engine()
    hasher = getattr(engine, '_run_request_hash', None)
    if callable(hasher):
        return hasher(session, question, answer_text, event)
    return _fallback_request_hash(session, question, answer_text, event)


def create_answer_execution(
    *,
    session: InterviewSession,
    question: InterviewQuestion,
    answer_text: str,
    client_idempotency_key: str,
    answered_count: int,
    media_context: dict | None = None,
) -> tuple[InterviewAgentExecution, InterviewQuestionGenerationJob, bool]:
    """Create the durable Agent run and dispatch outbox inside the answer transaction."""

    event = 'submit_answer_stream'
    request_hash = agent_request_hash(session, question, answer_text, event)
    now = timezone.now()
    engine = get_interview_agent_engine()
    engine_name = getattr(engine, 'engine_name', getattr(settings, 'INTERVIEW_AGENT_ENGINE', 'default'))
    state_schema_version = int(getattr(engine, 'state_schema_version', 4))
    run, _ = InterviewAgentRun.objects.get_or_create(
        session=session,
        event=event,
        request_hash=request_hash,
        defaults={
            'trigger_question': question,
            'engine_name': engine_name,
            'status': InterviewAgentRun.Status.PENDING,
            'state_schema_version': state_schema_version,
            'prompt_version': getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1'),
            'model_config_snapshot': (session.session_plan or {}).get('model_config_snapshot', {}),
        },
    )
    execution, created = InterviewAgentExecution.objects.get_or_create(
        session=session,
        event=event,
        idempotency_key=request_hash,
        defaults={
            'trigger_question': question,
            'legacy_run': run,
            'thread_id': session.id,
            'run_id': run.id,
            'request_hash': request_hash,
            'checkpoint_namespace': f'{event}:{run.id}',
            'engine_version': engine_name,
            'state_schema_version': state_schema_version,
            'status': InterviewAgentExecution.Status.ANSWER_PERSISTED,
            'version': 1,
            'started_at': now,
            'state_metadata': {
                'client_idempotency_key_hash': hashlib.sha256(client_idempotency_key.encode('utf-8')).hexdigest(),
                'answered_count': answered_count,
                'media_context': media_context or {},
            },
        },
    )
    if not created and execution.request_hash != request_hash:
        raise ValueError('agent_execution_request_hash_conflict')

    next_sequence = answered_count + 1
    generation_job, _ = InterviewQuestionGenerationJob.objects.get_or_create(
        session=session,
        sequence=next_sequence,
        defaults={
            'answered_question': question,
            'status': InterviewQuestionGenerationJob.Status.PENDING,
            'request_hash': request_hash,
            'engine_name': engine_name,
        },
    )
    if generation_job.answered_question_id != question.id:
        raise ValueError('generation_sequence_conflict')
    InterviewAgentDispatch.objects.get_or_create(execution=execution)
    return execution, generation_job, created


def cas_transition(
    execution_id,
    *,
    from_statuses: Iterable[str],
    to_status: str,
    expected_version: int | None = None,
    **updates,
) -> bool:
    queryset = InterviewAgentExecution.objects.filter(id=execution_id, status__in=tuple(from_statuses))
    if expected_version is not None:
        queryset = queryset.filter(version=expected_version)
    values = {'status': to_status, 'version': F('version') + 1, 'updated_at': timezone.now(), **updates}
    return queryset.update(**values) == 1


def durable_execution_snapshot(execution: InterviewAgentExecution) -> dict:
    result_question = execution.result_question
    generation_job = execution.session.question_generation_jobs.filter(
        answered_question_id=execution.trigger_question_id,
    ).select_related('generated_question').order_by('-created_at').first()
    payload = {
        'execution_id': str(execution.id),
        'run_id': str(execution.run_id),
        'thread_id': str(execution.thread_id),
        'status': execution.status,
        'version': execution.version,
        'retry_count': execution.retry_count,
        'last_durable_sequence': execution.last_durable_sequence,
        'error_code': execution.error_code,
        'fallback_reason': execution.fallback_reason,
        'updated_at': execution.updated_at.isoformat() if execution.updated_at else None,
        'result_question': None,
        'generation_job': None,
    }
    if result_question:
        payload['result_question'] = {
            'id': result_question.id,
            'sequence': result_question.sequence,
            'question_text': result_question.question_text,
        }
    if generation_job:
        payload['generation_job'] = {
            'id': generation_job.id,
            'status': generation_job.status,
            'sequence': generation_job.sequence,
            'partial_text': generation_job.partial_text,
            'final_text': generation_job.final_text,
            'error_message': generation_job.error_message,
            'generated_question_id': generation_job.generated_question_id,
        }
    return payload
