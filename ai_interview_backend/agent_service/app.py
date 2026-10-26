from __future__ import annotations

import hashlib
import os
from uuid import UUID

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_interview_backend.settings')

import django

django.setup()

from celery import current_app
from django.db import transaction
from django.utils import timezone
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from interviews.agent_v4.checkpoint import agent_database_url
from interviews.agent_v4.contracts import AgentEvent, AgentTurnInput
from interviews.agent_v4.events import read_agent_events
from interviews.execution import create_answer_execution
from interviews.models import InterviewQuestion, InterviewSession


app = FastAPI(title='iFaceoff Agent Service', version='4.0.0', docs_url=None, redoc_url=None)


def require_internal_token(authorization: str | None = Header(default=None)):
    expected = os.getenv('AGENT_SERVICE_TOKEN', '')
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='agent_service_token_not_configured')
    if authorization != f'Bearer {expected}':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_internal_token')


@app.get('/health')
def health():
    import psycopg

    try:
        with psycopg.connect(agent_database_url(), connect_timeout=2) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.checkpoints') IS NOT NULL")
                checkpoint_ready = bool(cursor.fetchone()[0])
        with current_app.connection_for_write().ensure_connection(max_retries=0):
            broker_ready = True
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={'code': type(exc).__name__},
        ) from None
    return {'ok': checkpoint_ready and broker_ready, 'checkpoint': checkpoint_ready, 'broker': broker_ready}


@app.post('/v1/turns', status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_internal_token)])
def create_turn(turn: AgentTurnInput):
    if turn.event != AgentEvent.SUBMIT_ANSWER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='unsupported_agent_event',
        )
    request_fingerprint = hashlib.sha256(turn.model_dump_json().encode('utf-8')).hexdigest()
    try:
        with transaction.atomic():
            session = InterviewSession.objects.select_for_update().get(
                id=turn.session_id,
                user_id=turn.user_id,
                status=InterviewSession.Status.RUNNING,
            )
            question = InterviewQuestion.objects.select_for_update().get(
                id=turn.question_id,
                session=session,
            )
            if question.answer_text and question.answer_text != turn.answer_text:
                raise ValueError('answer_conflicts_with_persisted_turn')
            if not question.answer_text:
                question.answer_text = turn.answer_text
                question.answered_at = timezone.now()
                question.save(update_fields=['answer_text', 'answered_at'])
            execution, _job, _created = create_answer_execution(
                session=session,
                question=question,
                answer_text=turn.answer_text,
                client_idempotency_key=request_fingerprint,
                answered_count=turn.answered_count,
                media_context=turn.media_context,
            )
    except (InterviewSession.DoesNotExist, InterviewQuestion.DoesNotExist):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='interview_turn_not_found') from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return {
        'accepted': True,
        'operation_id': str(execution.operation_id) if execution.operation_id else None,
        'execution_id': str(execution.id),
        'run_id': str(execution.run_id),
        'thread_id': str(turn.session_id),
        'events_url': (
            f'/api/v2/operations/{execution.operation_id}/events/'
            if execution.operation_id else f'/v1/runs/{execution.run_id}/events'
        ),
        'result_url': (
            f'/api/v2/operations/{execution.operation_id}/'
            if execution.operation_id else f'/v1/runs/{execution.run_id}/events'
        ),
        'agent_events_url': f'/v1/runs/{execution.run_id}/events',
    }


@app.get('/v1/runs/{run_id}/events', dependencies=[Depends(require_internal_token)])
def stream_run_events(run_id: UUID, last_event_id: str = '0-0'):
    def stream():
        cursor = last_event_id
        empty_reads = 0
        while empty_reads < 3:
            events = list(read_agent_events(run_id=run_id, after=cursor, block_ms=5000, count=100))
            if not events:
                empty_reads += 1
                yield ': heartbeat\n\n'
                continue
            empty_reads = 0
            for event in events:
                cursor = event.event_id
                yield event.to_sse()

    return StreamingResponse(stream(), media_type='text/event-stream')
