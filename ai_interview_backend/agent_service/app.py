from __future__ import annotations

import json
import os
from uuid import UUID

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_interview_backend.settings')

import django

django.setup()

from celery import current_app
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from interviews.agent_v4.checkpoint import agent_database_url
from interviews.agent_v4.contracts import AgentEvent, AgentTurnInput
from interviews.agent_v4.events import read_agent_events


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
    task = current_app.send_task(
        'interviews.tasks.run_composite_v4_turn',
        kwargs={'payload': json.loads(turn.model_dump_json())},
    )
    return {'accepted': True, 'task_id': task.id, 'thread_id': str(turn.session_id)}


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
