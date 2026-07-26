from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable

from django.conf import settings
from jsonschema import ValidationError, validate

from .configuration import assemble_generation_context


def user_can_manage_agent_system(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', '') in ('admin', 'hr')


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    subagent_name: str
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    permission_scope: str = 'session_owner'
    timeout_seconds: int | None = None
    fallback_strategy: str = 'degrade'
    audit_enabled: bool = True
    handler: Callable[..., Any] | None = None
    idempotent: bool = True
    max_retries: int = 0


@dataclass
class AgentToolExecution:
    name: str
    ok: bool
    status: str
    output: Any = None
    error: str = ''
    fallback_reason: str = ''
    latency_ms: int = 0
    attempts: int = 0
    permission_scope: str = ''
    subagent_name: str = ''


class AgentToolRegistry:
    def __init__(self):
        self._tools: dict[str, AgentToolSpec] = {}

    def register(self, spec: AgentToolSpec) -> AgentToolSpec:
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> AgentToolSpec | None:
        return self._tools.get(name)

    def list_specs(self) -> list[AgentToolSpec]:
        return list(self._tools.values())

    def is_allowed(self, name: str, *, user, session=None) -> bool:
        spec = self.get(name)
        if not spec:
            return False
        if spec.permission_scope == 'public_session':
            return bool(user and getattr(user, 'is_authenticated', False))
        if spec.permission_scope == 'session_owner':
            return bool(
                user
                and getattr(user, 'is_authenticated', False)
                and (
                    user_can_manage_agent_system(user)
                    or (session is not None and getattr(session, 'user_id', None) == getattr(user, 'id', None))
                )
            )
        if spec.permission_scope == 'admin_or_hr':
            return user_can_manage_agent_system(user)
        return False


class AgentToolExecutor:
    """Applies one permission, schema, timeout and retry policy to every tool."""

    def __init__(self, registry: AgentToolRegistry):
        self.registry = registry

    def execute(self, name: str, *, user, session=None, payload: dict | None = None) -> AgentToolExecution:
        spec = self.registry.get(name)
        if not spec:
            return AgentToolExecution(name=name, ok=False, status='failed', error='tool_not_registered')
        base = {
            'name': name,
            'permission_scope': spec.permission_scope,
            'subagent_name': spec.subagent_name,
        }
        if not self.registry.is_allowed(name, user=user, session=session):
            return AgentToolExecution(
                **base,
                ok=False,
                status='degraded' if spec.fallback_strategy != 'deny' else 'failed',
                error='tool_permission_denied',
                fallback_reason=spec.fallback_strategy,
            )
        payload = payload or {}
        try:
            if spec.input_schema:
                validate(instance=payload, schema=spec.input_schema)
        except ValidationError as exc:
            return AgentToolExecution(
                **base,
                ok=False,
                status='failed',
                error=f'input_schema_invalid:{exc.message}'[:300],
                fallback_reason=spec.fallback_strategy,
            )
        if not spec.handler:
            return AgentToolExecution(
                **base,
                ok=False,
                status='failed',
                error='tool_handler_missing',
                fallback_reason=spec.fallback_strategy,
            )

        max_attempts = 1 + (max(0, spec.max_retries) if spec.idempotent else 0)
        started = time.perf_counter()
        last_error = ''
        for attempt in range(1, max_attempts + 1):
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'agent-tool-{name}')
            future = pool.submit(spec.handler, **payload)
            try:
                output = future.result(timeout=spec.timeout_seconds)
                if spec.output_schema:
                    validate(instance=output, schema=spec.output_schema)
                pool.shutdown(wait=False, cancel_futures=True)
                return AgentToolExecution(
                    **base,
                    ok=True,
                    status='success',
                    output=output,
                    latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    attempts=attempt,
                )
            except FutureTimeoutError:
                last_error = 'tool_timeout'
                future.cancel()
            except ValidationError as exc:
                last_error = f'output_schema_invalid:{exc.message}'[:300]
            except Exception as exc:
                last_error = str(exc)[:300] or exc.__class__.__name__
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        return AgentToolExecution(
            **base,
            ok=False,
            status='degraded' if spec.fallback_strategy != 'deny' else 'failed',
            error=last_error,
            fallback_reason=spec.fallback_strategy,
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            attempts=max_attempts,
        )


class AgentHookManager:
    def __init__(self):
        self._hooks: dict[str, list[Callable[..., dict | None]]] = {}

    def register(self, name: str, handler: Callable[..., dict | None]) -> None:
        self._hooks.setdefault(name, []).append(handler)

    def run(self, name: str, **payload) -> list[dict]:
        events = []
        for handler in self._hooks.get(name, []):
            try:
                result = handler(**payload) or {}
                events.append({'hook': name, 'status': 'ok', 'result': result})
            except Exception as exc:
                events.append({'hook': name, 'status': 'failed', 'error': str(exc)[:300]})
        return events


class AgentSlashCommandRegistry:
    def __init__(self):
        self._commands: dict[str, dict] = {}

    def register(self, command: str, *, description: str, permission_scope: str = 'admin_or_hr') -> None:
        normalized = command if command.startswith('/') else f'/{command}'
        self._commands[normalized] = {
            'command': normalized,
            'description': description,
            'permission_scope': permission_scope,
        }

    def parse(self, text: str) -> dict:
        text = (text or '').strip()
        if not text.startswith('/'):
            return {'is_command': False}
        parts = text.split(maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ''
        spec = self._commands.get(command)
        return {
            'is_command': True,
            'command': command,
            'args': args,
            'known': bool(spec),
            'permission_scope': (spec or {}).get('permission_scope', 'admin_or_hr'),
        }

    def list_commands(self) -> list[dict]:
        return list(self._commands.values())


class ContextBudgetManager:
    def __init__(self, token_budget: int | None = None):
        self.token_budget = int(token_budget or getattr(settings, 'AGENT_CONTEXT_TOKEN_BUDGET', 6000))

    def approximate_tokens(self, value: Any) -> int:
        text = str(value or '')
        # Chinese text usually tokenizes denser than English; this is a conservative local budget estimate.
        return max(1, len(text) // 2)

    def compress(self, *, session, history: list, rag_context: list, memory_events: list, media_context: dict) -> dict:
        if getattr(session, 'agent_config_snapshot', None):
            return assemble_generation_context(
                session=session,
                history=history,
                rag_context=rag_context,
                memory_events=memory_events,
                media_context=media_context,
                task_context={},
            )
        memory = session.memory_summary or {}
        required = {
            'job_position': session.job_position,
            'stage': session.current_stage,
            'session_plan_keys': list((session.session_plan or {}).keys()),
            'current_strategy': memory.get('question_strategy', ''),
            'coverage_gaps': (memory.get('coverage_gaps') or [])[:8],
            'pending_topics': (session.pending_topics or memory.get('pending_topics') or [])[:8],
        }
        compressed_history = [
            {
                'question': item.get('question', '')[:220],
                'answer': item.get('answer', '')[:260],
                'evaluation': {
                    'final_score': (item.get('evaluation') or {}).get('final_score'),
                    'follow_up_target': (item.get('evaluation') or {}).get('follow_up_target'),
                    'risk_flags': (item.get('evaluation') or {}).get('risk_flags', [])[:5],
                },
            }
            for item in (history or [])[-6:]
            if isinstance(item, dict)
        ]
        evidence = [
            {
                'document_id': item.get('document_id'),
                'chunk_id': item.get('chunk_id'),
                'title': item.get('title'),
                'visibility': item.get('visibility'),
                'ability_tags': item.get('ability_tags', [])[:6],
                'score': item.get('score'),
                'rerank_score': item.get('rerank_score'),
                'content': (item.get('content') or '')[:600],
                'content_preview_hash': hashlib.sha256((item.get('content') or '').encode('utf-8')).hexdigest()[:16],
            }
            for item in (rag_context or [])[:6]
            if isinstance(item, dict)
        ]
        recall = [
            {
                'event_type': item.get('event_type'),
                'memory_key': item.get('memory_key'),
                'importance': item.get('importance'),
                'source_node': item.get('source_node'),
                'value_summary': item.get('value_summary'),
            }
            for item in (memory_events or [])[:8]
            if isinstance(item, dict)
        ]
        summary = {
            'token_budget': self.token_budget,
            'estimated_tokens': 0,
            'required': required,
            'history': compressed_history,
            'rag_evidence': evidence,
            'memory_recall': recall,
            'media_context': {
                'has_audio': bool((media_context or {}).get('has_audio')),
                'asr_confidence': ((media_context or {}).get('asr_transcript_meta') or {}).get('confidence'),
            },
            'injection_policy': {
                'required': ['system_policy', 'session_plan', 'current_question', 'answer', 'rubric'],
                'optional': ['rag_evidence', 'memory_recall', 'history_summary', 'media_context'],
                'forbidden': ['other_tenant_private_knowledge', 'unapproved_knowledge', 'unsupported_claims'],
            },
            'dropped': [],
            'section_tokens': {},
        }
        for key in ('required', 'history', 'rag_evidence', 'memory_recall', 'media_context'):
            summary['section_tokens'][key] = self.approximate_tokens(summary[key])
        summary['estimated_tokens'] = self.approximate_tokens(summary)
        while summary['estimated_tokens'] > self.token_budget and len(summary['history']) > 2:
            summary['history'].pop(0)
            summary['dropped'].append('oldest_history')
            summary['estimated_tokens'] = self.approximate_tokens(summary)
        while summary['estimated_tokens'] > self.token_budget and len(summary['memory_recall']) > 3:
            summary['memory_recall'].pop()
            summary['dropped'].append('low_priority_memory')
            summary['estimated_tokens'] = self.approximate_tokens(summary)
        while summary['estimated_tokens'] > self.token_budget and len(summary['rag_evidence']) > 2:
            summary['rag_evidence'].pop()
            summary['dropped'].append('lower_ranked_rag')
            summary['estimated_tokens'] = self.approximate_tokens(summary)
        if summary['estimated_tokens'] > self.token_budget:
            for item in summary['rag_evidence']:
                item['content'] = item.get('content', '')[:240]
            summary['dropped'].append('rag_content_truncated')
            summary['estimated_tokens'] = self.approximate_tokens(summary)
        return summary


def normalize_prompt_version(value: str = '') -> str:
    value = (value or getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1')).strip()
    return re.sub(r'[^a-zA-Z0-9_.:-]', '-', value)[:80] or 'interview-agent-v1'


def build_default_tool_registry() -> AgentToolRegistry:
    timeout = int(getattr(settings, 'AGENT_TOOL_TIMEOUT_SECONDS', 30))
    registry = AgentToolRegistry()
    registry.register(AgentToolSpec(
        name='knowledge.hybrid_search',
        subagent_name='RetrievalAgent',
        input_schema={'type': 'object', 'required': ['job_position', 'stage', 'pending_topics']},
        output_schema={'type': 'object', 'required': ['source_count', 'retrieval_trace']},
        permission_scope='session_owner',
        timeout_seconds=timeout,
        fallback_strategy='continue_without_rag',
        max_retries=1,
    ))
    registry.register(AgentToolSpec(
        name='rubric.rule_evaluate',
        subagent_name='EvaluationAgent',
        permission_scope='session_owner',
        timeout_seconds=timeout,
        fallback_strategy='rule_only_degraded',
        max_retries=0,
    ))
    registry.register(AgentToolSpec(
        name='question.validate',
        subagent_name='SafetyAgent',
        permission_scope='session_owner',
        timeout_seconds=timeout,
        fallback_strategy='regenerate_or_clarify',
        max_retries=0,
    ))
    registry.register(AgentToolSpec(
        name='speech.asr',
        subagent_name='ConversationAgent',
        permission_scope='session_owner',
        timeout_seconds=timeout,
        fallback_strategy='manual_text_input',
        max_retries=1,
    ))
    registry.register(AgentToolSpec(
        name='speech.tts',
        subagent_name='ConversationAgent',
        permission_scope='session_owner',
        timeout_seconds=timeout,
        fallback_strategy='browser_tts',
        max_retries=1,
    ))
    registry.register(AgentToolSpec(
        name='agent.debug',
        subagent_name='SafetyAgent',
        permission_scope='admin_or_hr',
        timeout_seconds=timeout,
        fallback_strategy='deny',
        idempotent=False,
    ))
    return registry


def build_default_slash_commands() -> AgentSlashCommandRegistry:
    registry = AgentSlashCommandRegistry()
    registry.register('/trace', description='查看当前会话 Agent Trace')
    registry.register('/retry-next-question', description='重试下一题生成')
    registry.register('/reindex-knowledge', description='触发知识库重建索引')
    registry.register('/preview-chunks', description='预览知识库切块')
    registry.register('/agent-memory', description='查看当前会话 Agent 记忆')
    return registry
