from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from django.conf import settings
from django_redis import get_redis_connection

from interviews.models import InterviewAgentExecution
from interviews.execution import durable_execution_snapshot

from .contracts import AgentStreamEvent


def _stream_key(run_id: UUID | str) -> str:
    return f'ifaceoff:agent-events:{run_id}'


def publish_agent_event(*, thread_id, run_id, event_type: str, sequence: int, payload: dict[str, Any]) -> AgentStreamEvent:
    base = {
        'schema_version': 1,
        'thread_id': str(thread_id),
        'run_id': str(run_id),
        'type': event_type,
        'sequence': sequence,
        'payload': payload,
    }
    try:
        redis = get_redis_connection('realtime')
        redis_id = redis.xadd(
            _stream_key(run_id),
            {'event': json.dumps(base, ensure_ascii=False, separators=(',', ':'))},
            maxlen=int(getattr(settings, 'AGENT_EVENT_STREAM_MAXLEN', 2000)),
            approximate=True,
        ).decode()
        redis.expire(_stream_key(run_id), int(getattr(settings, 'AGENT_EVENT_STREAM_TTL_SECONDS', 86400)))
    except Exception:
        redis_id = f'local-{sequence}'
    event = AgentStreamEvent.model_validate({
        **base,
        'event_id': redis_id,
        'thread_id': UUID(str(thread_id)),
        'run_id': UUID(str(run_id)),
    })
    InterviewAgentExecution.objects.filter(run_id=run_id).update(last_event_id=event.event_id)
    return event


def read_agent_events(*, run_id, after='0-0', block_ms=0, count=100) -> Iterator[AgentStreamEvent]:
    redis = get_redis_connection('realtime')
    options = {'count': count}
    if block_ms:
        options['block'] = block_ms
    result = redis.xread({_stream_key(run_id): after or '0-0'}, **options)
    for _, messages in result:
        for redis_id, fields in messages:
            raw = fields.get(b'event') or fields.get('event')
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            payload = json.loads(raw)
            yield AgentStreamEvent.model_validate({
                **payload,
                'event_id': redis_id.decode() if isinstance(redis_id, bytes) else str(redis_id),
                'thread_id': UUID(str(payload['thread_id'])),
                'run_id': UUID(str(payload['run_id'])),
            })


def durable_snapshot_event(execution: InterviewAgentExecution) -> AgentStreamEvent:
    sequence = int(execution.last_durable_sequence or 0)
    return AgentStreamEvent.model_validate({
        'schema_version': 1,
        'event_id': f'durable-{execution.version}-{sequence}',
        'thread_id': UUID(str(execution.thread_id)),
        'run_id': UUID(str(execution.run_id)),
        'type': 'state.snapshot',
        'sequence': sequence,
        'payload': durable_execution_snapshot(execution),
    })
