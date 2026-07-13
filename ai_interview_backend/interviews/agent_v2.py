from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from system.ai_config import resolve_ai_config
from system.models import AIModel

from .agent import CompositeInterviewAgentEngine, InterviewAgentState, _json_safe
from .agent_runtime import AgentToolExecutor, AgentToolSpec
from .ai_services import generate_next_question_stream
from .evaluation import (
    combine_rule_and_ai_evaluation,
    rule_evaluate_answer,
    summarize_report_scores,
    update_session_coverage_targeted,
    validate_generated_question,
)
from .models import (
    InterviewAgentMemoryEvent,
    InterviewAgentNodeRun,
    InterviewAgentRun,
    InterviewQuestion,
    InterviewSession,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InterviewSubAgent:
    name: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()
    timeout_seconds: int = 30
    max_retries: int = 0
    fallback_strategy: str = 'fail'


SUBAGENT_CONTRACTS = {
    'load_context': InterviewSubAgent('ConversationAgent', ('session_id', 'question_id', 'user_id'), ('session_snapshot',)),
    'normalize_input': InterviewSubAgent('ConversationAgent', ('answer_text',), ('media_context',)),
    'rule_evaluate': InterviewSubAgent('EvaluationAgent', ('question_text', 'answer_text'), ('rule_evaluation',), ('rubric.rule_evaluate',)),
    'ai_evaluate': InterviewSubAgent('EvaluationAgent', ('question_text', 'answer_text'), ('answer_evaluation',), ('model.answer_evaluate',), fallback_strategy='rule_only_degraded'),
    'rule_degrade': InterviewSubAgent('EvaluationAgent', ('rule_evaluation',), ('answer_evaluation',), fallback_strategy='rule_only_degraded'),
    'evidence_guard': InterviewSubAgent('EvidenceGuardAgent', ('answer_evaluation', 'answer_text'), ('answer_evaluation',)),
    'update_coverage': InterviewSubAgent('EvaluationAgent', ('answer_evaluation', 'current_question_plan'), ('coverage_summary',)),
    'update_memory': InterviewSubAgent('MemoryAgent', ('history', 'answer_evaluation'), ('interview_finished',)),
    'recall_memory': InterviewSubAgent('MemoryAgent', ('session_id',), ('retrieved_memory_events',)),
    'strategy_plan': InterviewSubAgent('StrategyAgent', ('history', 'coverage_summary'), ('question_plan', 'retrieval_intent')),
    'retrieve': InterviewSubAgent('RetrievalAgent', ('question_plan',), ('rag_context', 'retrieval_trace'), ('knowledge.hybrid_search',), fallback_strategy='continue_without_rag'),
    'skip_rag': InterviewSubAgent('RetrievalAgent', ('question_plan',), ('rag_context', 'retrieval_trace'), fallback_strategy='continue_without_rag'),
    'assemble_context': InterviewSubAgent('MemoryAgent', ('question_plan', 'rag_context'), ('generation_context', 'context_budget')),
    'ingest_generation': InterviewSubAgent('QuestionAgent', ('generated_text',), ('generated_text',)),
    'validate': InterviewSubAgent('SafetyAgent', ('generated_text', 'question_plan'), ('validation_errors',), ('question.validate',)),
    'repair': InterviewSubAgent('QuestionAgent', ('validation_errors',), ('generated_text', 'generation_attempt'), ('model.question_generate',), max_retries=2, fallback_strategy='safe_fallback'),
    'safe_fallback': InterviewSubAgent('SafetyAgent', ('question_plan',), ('generated_text', 'validation_errors'), fallback_strategy='deterministic_question'),
    'persist': InterviewSubAgent('ConversationAgent', ('generated_text', 'question_plan'), ('generated_question_id',)),
    'reflect': InterviewSubAgent('MemoryAgent', ('generated_question_id',), ('run_completed',)),
    'report_collect': InterviewSubAgent('ReportAgent', ('session_id',), ('report_evidence',)),
    'report_generate': InterviewSubAgent('ReportAgent', ('report_evidence',), ('report_data',)),
    'report_validate': InterviewSubAgent('EvidenceGuardAgent', ('report_data',), ('report_data', 'report_validation_errors')),
}


class CompositeV2InterviewAgentEngine(CompositeInterviewAgentEngine):
    """Recoverable conditional graph while preserving the public interview API."""

    engine_name = 'composite_v2'

    def __init__(self):
        super().__init__()
        timeout = int(getattr(settings, 'AGENT_NODE_TIMEOUT_SECONDS', 30))
        self.max_generation_retries = int(getattr(settings, 'AGENT_MAX_GENERATION_RETRIES', 2))
        self.state_schema_version = int(getattr(settings, 'AGENT_STATE_SCHEMA_VERSION', 2))
        self.confidence_threshold = float(getattr(settings, 'AGENT_EVALUATION_CONFIDENCE_THRESHOLD', 0.6))
        self._register_v2_tool('model.answer_evaluate', 'EvaluationAgent', timeout, 'rule_only_degraded', False)
        self._register_v2_tool('model.question_generate', 'QuestionAgent', timeout, 'safe_fallback', False)
        self.tool_executor = AgentToolExecutor(self.tool_registry)
        self._prepare_graph = self._compile_prepare_graph()
        self._finalize_graph = self._compile_finalize_graph()
        self._report_graph = self._compile_report_graph()

    def _register_v2_tool(self, name, subagent, timeout, fallback, idempotent):
        self.tool_registry.register(AgentToolSpec(
            name=name,
            subagent_name=subagent,
            permission_scope='session_owner',
            timeout_seconds=timeout,
            fallback_strategy=fallback,
            idempotent=idempotent,
        ))

    def _compile_prepare_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            logger.warning('Composite V2 prepare graph unavailable: %s', exc)
            return None
        graph = StateGraph(dict)
        for name, func in (
            ('load_context', self._node_load_context),
            ('normalize_input', self._node_normalize_input),
            ('rule_evaluate', self._node_rule_evaluate),
            ('ai_evaluate', self._node_ai_evaluate),
            ('rule_degrade', self._node_rule_degrade),
            ('evidence_guard', self._node_evidence_guard),
            ('update_coverage', self._node_update_coverage_v2),
            ('update_memory', self._node_update_memory_v2),
            ('recall_memory', self._node_recall_memory),
            ('strategy_plan', self._node_strategy_plan),
            ('retrieve', self._node_retrieve_v2),
            ('skip_rag', self._node_skip_rag),
            ('assemble_context', self._node_assemble_context),
        ):
            graph.add_node(name, self._wrap_node(name, func))
        graph.set_entry_point('load_context')
        graph.add_edge('load_context', 'normalize_input')
        graph.add_edge('normalize_input', 'rule_evaluate')
        graph.add_conditional_edges('rule_evaluate', self._route_ai, {'ai': 'ai_evaluate', 'degrade': 'rule_degrade'})
        graph.add_edge('ai_evaluate', 'evidence_guard')
        graph.add_edge('rule_degrade', 'evidence_guard')
        graph.add_edge('evidence_guard', 'update_coverage')
        graph.add_edge('update_coverage', 'update_memory')
        graph.add_edge('update_memory', 'recall_memory')
        graph.add_edge('recall_memory', 'strategy_plan')
        graph.add_conditional_edges('strategy_plan', self._route_retrieval, {'retrieve': 'retrieve', 'skip': 'skip_rag'})
        graph.add_edge('retrieve', 'assemble_context')
        graph.add_edge('skip_rag', 'assemble_context')
        graph.add_edge('assemble_context', END)
        return graph.compile()

    def _compile_finalize_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            logger.warning('Composite V2 finalize graph unavailable: %s', exc)
            return None
        graph = StateGraph(dict)
        for name, func in (
            ('ingest_generation', self._node_ingest_generation),
            ('validate', self._node_validate),
            ('repair', self._node_repair),
            ('safe_fallback', self._node_safe_fallback),
            ('persist', self._node_persist),
            ('reflect', self._node_reflect),
        ):
            graph.add_node(name, self._wrap_node(name, func))
        graph.set_entry_point('ingest_generation')
        graph.add_edge('ingest_generation', 'validate')
        graph.add_conditional_edges('validate', self._route_validation, {
            'persist': 'persist',
            'repair': 'repair',
            'fallback': 'safe_fallback',
        })
        graph.add_edge('repair', 'validate')
        graph.add_edge('safe_fallback', 'persist')
        graph.add_edge('persist', 'reflect')
        graph.add_edge('reflect', END)
        return graph.compile()

    def _compile_report_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            logger.warning('Composite V2 report graph unavailable: %s', exc)
            return None
        graph = StateGraph(dict)
        for name, func in (
            ('report_collect', self._node_report_collect),
            ('report_generate', self._node_report_generate),
            ('report_validate', self._node_report_validate),
        ):
            graph.add_node(name, self._wrap_node(name, func))
        graph.set_entry_point('report_collect')
        graph.add_edge('report_collect', 'report_generate')
        graph.add_edge('report_generate', 'report_validate')
        graph.add_edge('report_validate', END)
        return graph.compile()

    def _wrap_node(self, name: str, func: Callable[[dict], dict]):
        def wrapped(payload: dict):
            state = payload.get('state') or {}
            return {'state': self._run_node(name, state, func)}
        return wrapped

    def _run_node(self, name: str, state: dict, func: Callable[[dict], dict]) -> dict:
        contract = SUBAGENT_CONTRACTS[name]
        missing = [key for key in contract.required_inputs if key not in state]
        if missing:
            raise ValueError(f'{name}:missing_inputs:{",".join(missing)}')
        input_hash = self._hash_payload({key: state.get(key) for key in contract.required_inputs})
        with transaction.atomic():
            run = InterviewAgentRun.objects.select_for_update().get(id=state['run_id'])
            attempt = run.node_runs.filter(node_name=name).count() + 1
            node_run = InterviewAgentNodeRun.objects.create(
                run=run,
                node_name=name,
                subagent_name=contract.name,
                status=InterviewAgentNodeRun.Status.RUNNING,
                attempt=attempt,
                input_hash=input_hash,
                started_at=timezone.now(),
            )
            run.current_node = name
            run.status = InterviewAgentRun.Status.RUNNING
            run.attempt_count = max(run.attempt_count, attempt)
            run.save(update_fields=['current_node', 'status', 'attempt_count', 'updated_at'])
        started = time.perf_counter()
        try:
            delta = func(dict(state)) or {}
            missing_outputs = [key for key in contract.required_outputs if key not in delta]
            if missing_outputs:
                raise ValueError(f'{name}:missing_outputs:{",".join(missing_outputs)}')
            merged = {**state, **delta}
            merged.setdefault('node_order', []).append(name)
            node_outputs = merged.setdefault('node_outputs', {})
            node_outputs[name] = self._node_summary(delta, contract.name)
            node_status = delta.pop('_node_status', InterviewAgentNodeRun.Status.SUCCEEDED)
            node_run.status = node_status
            node_run.output_summary = _json_safe(self._node_summary(delta, contract.name))
            node_run.fallback_reason = str(delta.get('fallback_reason') or '')[:200]
            node_run.latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            node_run.completed_at = timezone.now()
            node_run.save(update_fields=['status', 'output_summary', 'fallback_reason', 'latency_ms', 'completed_at'])
            run.state_snapshot = self._snapshot_state(merged)
            run.fallback_reason = str(merged.get('fallback_reason') or '')[:200]
            run.save(update_fields=['state_snapshot', 'fallback_reason', 'updated_at'])
            return merged
        except Exception as exc:
            node_run.status = InterviewAgentNodeRun.Status.FAILED
            node_run.error_message = str(exc)[:2000]
            node_run.latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            node_run.completed_at = timezone.now()
            node_run.save(update_fields=['status', 'error_message', 'latency_ms', 'completed_at'])
            run.status = InterviewAgentRun.Status.FAILED
            run.error_message = str(exc)[:2000]
            run.save(update_fields=['status', 'error_message', 'updated_at'])
            raise

    def _node_summary(self, delta: dict, subagent: str) -> dict:
        summary = {'subagent': subagent}
        for key, value in delta.items():
            if key in ('history', 'resume_text', 'jd_text', 'answer_text', 'answer', 'question', 'question_text', 'generated_text'):
                summary[f'{key}_length'] = len(str(value or ''))
            elif key in ('rag_context', 'contexts'):
                summary['rag_context'] = [
                    {'chunk_id': item.get('chunk_id'), 'document_id': item.get('document_id'), 'score': item.get('score')}
                    for item in (value or [])[:6] if isinstance(item, dict)
                ]
            elif key in ('generation_context', 'compressed_context_summary'):
                summary[key] = {
                    'estimated_tokens': (value or {}).get('estimated_tokens'),
                    'token_budget': (value or {}).get('token_budget'),
                    'target_dimension': (value or {}).get('target_dimension'),
                    'rag_source_ids': [item.get('chunk_id') for item in (value or {}).get('rag_evidence', []) if isinstance(item, dict)],
                    'dropped': (value or {}).get('dropped', []),
                }
            elif key == 'report_evidence':
                summary[key] = {
                    'turn_count': len((value or {}).get('turns') or []),
                    'coverage_gaps': ((value or {}).get('coverage_summary') or {}).get('coverage_gaps', []),
                    'supported_evidence_count': sum(
                        len(item.get('evidence_items') or [])
                        for item in (value or {}).get('turns') or [] if isinstance(item, dict)
                    ),
                }
            elif hasattr(value, 'pk'):
                summary[key] = {'type': value.__class__.__name__, 'id': str(value.pk)}
            else:
                summary[key] = self._audit_safe(value)
        return _json_safe(summary)

    def _audit_safe(self, value: Any):
        if isinstance(value, dict):
            return {str(key): self._audit_safe(item) for key, item in value.items() if 'api_key' not in str(key).lower()}
        if isinstance(value, (list, tuple)):
            return [self._audit_safe(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, 'pk'):
            return {'type': value.__class__.__name__, 'id': str(value.pk)}
        return str(value)[:300]

    def _snapshot_state(self, state: dict) -> dict:
        allowed = (
            'run_id', 'session_id', 'question_id', 'user_id', 'event', 'answered_count',
            'session_snapshot', 'media_context', 'rule_evaluation', 'answer_evaluation',
            'coverage_summary', 'interview_finished', 'retrieved_memory_events', 'question_plan',
            'retrieval_intent', 'rag_context', 'retrieval_trace', 'generation_context',
            'context_budget', 'generated_text', 'generation_attempt', 'validation_errors',
            'fallback_reason', 'generated_question_id', 'node_order', 'node_outputs',
            'report_data', 'report_validation_errors',
        )
        snapshot = {key: state.get(key) for key in allowed if key in state}
        if 'generated_text' in snapshot:
            snapshot['generated_text'] = str(snapshot['generated_text'] or '')[:2000]
        return _json_safe(snapshot)

    def _hash_payload(self, value: Any) -> str:
        return hashlib.sha256(json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    def _route_ai(self, payload: dict) -> str:
        return 'ai' if (payload.get('state') or {}).get('ai_available') else 'degrade'

    def _route_retrieval(self, payload: dict) -> str:
        state = payload.get('state') or {}
        return 'retrieve' if state.get('retrieval_intent') and not state.get('interview_finished') else 'skip'

    def _route_validation(self, payload: dict) -> str:
        state = payload.get('state') or {}
        if not state.get('validation_errors'):
            return 'persist'
        if int(state.get('generation_attempt') or 0) < self.max_generation_retries:
            return 'repair'
        return 'fallback'

    def _node_load_context(self, state: dict) -> dict:
        session = InterviewSession.objects.select_related('user').get(id=state['session_id'])
        question = session.questions.get(id=state['question_id'])
        config = resolve_ai_config(session.user, AIModel.ModelType.CHAT)
        return {
            'session_snapshot': {
                'job_position': session.job_position,
                'difficulty': session.difficulty,
                'current_stage': session.current_stage,
                'question_count': session.question_count,
                'session_plan': session.session_plan or {},
                'template_snapshot': session.template_snapshot or {},
                'covered_topics': session.covered_topics or [],
                'pending_topics': session.pending_topics or [],
                'memory_summary': session.memory_summary or {},
            },
            'question_text': question.question_text,
            'current_question_plan': question.question_plan or {},
            'analysis_data': question.analysis_data or [],
            'ai_available': bool(config.api_key and config.model),
            'model_config_snapshot': {
                'provider': getattr(config.model, 'provider', '') if config.model else '',
                'model_slug': getattr(config.model, 'model_slug', '') if config.model else '',
                'source': config.source,
                'has_api_key': bool(config.api_key),
            },
        }

    def _node_normalize_input(self, state: dict) -> dict:
        media = state.get('media_context') or {}
        meta = media.get('asr_transcript_meta') or {}
        try:
            confidence = float(meta.get('confidence')) if meta.get('confidence') not in (None, '') else None
        except (TypeError, ValueError):
            confidence = None
        return {'media_context': {
            'audio_artifact_id': media.get('audio_artifact_id') or '',
            'has_audio': bool(media.get('audio_artifact_id')),
            'asr_transcript_meta': meta,
            'asr_confidence': confidence,
            'needs_confirmation': confidence is not None and confidence < getattr(settings, 'ASR_MIN_CONFIDENCE', 0.65),
        }}

    def _execute_tool(self, name: str, state: dict, handler: Callable[..., Any], payload: dict) -> Any:
        spec = self.tool_registry.get(name)
        self.tool_registry.register(replace(spec, handler=handler) if spec else AgentToolSpec(
            name=name, subagent_name='ConversationAgent', handler=handler,
        ))
        session = InterviewSession.objects.get(id=state['session_id'])
        result = self.tool_executor.execute(name, user=session.user, session=session, payload=payload)
        state.setdefault('tool_calls', []).append({
            'name': name,
            'ok': result.ok,
            'status': result.status,
            'input_summary': self._node_summary(payload, result.subagent_name),
            'output_summary': self._node_summary(result.output if isinstance(result.output, dict) else {'value': result.output}, result.subagent_name),
            'error': result.error,
            'fallback_reason': result.fallback_reason,
            'latency_ms': result.latency_ms,
            'attempts': result.attempts,
            'permission_scope': result.permission_scope,
            'subagent_name': result.subagent_name,
        })
        return result

    def _node_rule_evaluate(self, state: dict) -> dict:
        result = self._execute_tool(
            'rubric.rule_evaluate', state,
            lambda **kwargs: rule_evaluate_answer(**kwargs),
            {'question': state['question_text'], 'answer': state['answer_text'], 'session_plan': state['session_snapshot']['session_plan']},
        )
        if not result.ok:
            raise RuntimeError(result.error or 'rule_evaluation_failed')
        return {'rule_evaluation': result.output, 'tool_calls': state.get('tool_calls', [])}

    def _node_ai_evaluate(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        result = self._execute_tool(
            'model.answer_evaluate', state,
            lambda **kwargs: self.evaluate_answer(**kwargs),
            {
                'job_position': session.job_position,
                'question': state['question_text'],
                'answer': state['answer_text'],
                'user': session.user,
                'jd_text': state.get('jd_text') or '',
            },
        )
        ai_result = result.output if result.ok and isinstance(result.output, dict) else {}
        combined = combine_rule_and_ai_evaluation(state['rule_evaluation'], ai_result)
        if not result.ok:
            combined['evaluation_mode'] = 'rule_only_degraded'
            combined['degraded_reason'] = result.error or 'ai_evaluation_failed'
        return {'answer_evaluation': combined, 'tool_calls': state.get('tool_calls', [])}

    def _node_rule_degrade(self, state: dict) -> dict:
        combined = combine_rule_and_ai_evaluation(state['rule_evaluation'], {})
        combined['degraded_reason'] = 'ai_model_unavailable'
        return {'answer_evaluation': combined, 'fallback_reason': 'ai_model_unavailable', '_node_status': InterviewAgentNodeRun.Status.DEGRADED}

    def _node_evidence_guard(self, state: dict) -> dict:
        evaluation = dict(state['answer_evaluation'] or {})
        answer_compact = ''.join(str(state['answer_text']).split()).lower()
        supported = []
        rejected = []
        for item in evaluation.get('evidence_items') or []:
            if not isinstance(item, dict):
                continue
            quote = str(item.get('quote') or '').strip()
            quote_compact = ''.join(quote.split()).lower()
            valid = bool(quote_compact and quote_compact in answer_compact)
            checked = {**item, 'supported': valid, 'source': 'candidate_answer'}
            (supported if valid else rejected).append(checked)
        evaluation['evidence_items'] = supported
        evaluation['rejected_evidence_items'] = rejected
        evaluation['unsupported_claim'] = bool(rejected)
        if rejected:
            for key in ('strengths', 'risks', 'verified_abilities'):
                evaluation.pop(key, None)
        return {'answer_evaluation': evaluation, 'evidence_guard': {'supported': len(supported), 'rejected': len(rejected)}}

    def _node_update_coverage_v2(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        question = session.questions.get(id=state['question_id'])
        evaluation = {**state['answer_evaluation'], 'agent_run_id': str(state['run_id'])}
        if isinstance(question.ai_feedback, dict) and question.ai_feedback.get('agent_run_id') == str(state['run_id']):
            return {'coverage_summary': session.coverage_summary or {}, 'answer_evaluation': question.ai_feedback, '_node_status': InterviewAgentNodeRun.Status.SKIPPED}
        question.ai_feedback = evaluation
        question.evaluated_at = timezone.now()
        question.save(update_fields=['ai_feedback', 'evaluated_at'])
        summary = update_session_coverage_targeted(
            session,
            evaluation,
            state.get('current_question_plan') or {},
            confidence_threshold=self.confidence_threshold,
        )
        return {'coverage_summary': summary, 'answer_evaluation': evaluation}

    def _node_update_memory_v2(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        finished = int(state.get('answered_count') or 0) >= session.question_count
        if finished:
            return {'interview_finished': True, '_node_status': InterviewAgentNodeRun.Status.SKIPPED}
        next_stage = self.decide_stage(
            next_sequence=int(state.get('answered_count') or 0) + 1,
            total_questions=session.question_count,
            has_resume=bool(state.get('resume_text')),
        )
        refreshed = self.update_memory(
            job_position=session.job_position,
            user=session.user,
            history=state.get('history') or [],
            current_stage=next_stage,
            resume_text=state.get('resume_text') or '',
            jd_text=state.get('jd_text') or '',
        )
        preserved = session.memory_summary or {}
        for key in ('asked_question_signatures', 'used_knowledge_chunks', 'tool_observations', 'last_tool_observation'):
            if preserved.get(key) and not refreshed.get(key):
                refreshed[key] = preserved[key]
        refreshed['adaptive_difficulty'] = self.decide_difficulty(
            base_difficulty=session.difficulty,
            recent_feedback=[item.get('evaluation') for item in state.get('history') or [] if isinstance(item.get('evaluation'), dict)],
            current_stage=next_stage,
        )
        refreshed['coverage_gaps'] = (state.get('coverage_summary') or {}).get('coverage_gaps', [])
        session.current_stage = next_stage
        session.memory_summary = refreshed
        session.covered_topics = refreshed.get('covered_topics', [])
        session.pending_topics = refreshed.get('pending_topics', [])
        session.save(update_fields=['current_stage', 'memory_summary', 'covered_topics', 'pending_topics', 'updated_at'])
        return {'interview_finished': False, 'session_snapshot': {**state['session_snapshot'], 'current_stage': next_stage, 'memory_summary': refreshed, 'covered_topics': session.covered_topics, 'pending_topics': session.pending_topics}}

    def _node_recall_memory(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        events = self.load_relevant_memory_events(session=session)
        return {'retrieved_memory_events': events}

    def _node_strategy_plan(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        if state.get('interview_finished'):
            return {'question_plan': {'stage': session.current_stage, 'target': 'finish_interview', 'retrieval_intent': False}, 'retrieval_intent': False}
        session.memory_summary = {
            **(session.memory_summary or {}),
            'retrieved_memory_events': state.get('retrieved_memory_events') or [],
            'coverage_gaps': (state.get('coverage_summary') or {}).get('coverage_gaps', []),
        }
        plan = self.plan_next_question(
            session=session,
            history=state.get('history') or [],
            rag_context=[],
            last_evaluation=state.get('answer_evaluation') or {},
        )
        plan['target_stage'] = plan.get('target_stage') or session.current_stage
        plan['target_dimension'] = plan.get('target_dimension') or plan.get('target_gap') or ''
        plan['difficulty'] = plan.get('difficulty') or session.difficulty
        retrieval_intent = bool(
            not plan.get('needs_audio_confirmation')
            and (plan.get('target_dimension') or plan.get('target_gap') or session.current_stage != InterviewSession.InterviewStage.OPENING)
        )
        plan['retrieval_intent'] = retrieval_intent
        session.memory_summary = {**(session.memory_summary or {}), 'stage_plan': plan}
        session.save(update_fields=['memory_summary', 'updated_at'])
        return {'question_plan': plan, 'retrieval_intent': retrieval_intent}

    def _node_retrieve_v2(self, state: dict) -> dict:
        session = InterviewSession.objects.select_related('user').get(id=state['session_id'])
        plan = state['question_plan']

        def handler(**kwargs):
            contexts = self.retrieve_knowledge(
                session=session,
                history=state.get('history') or [],
                resume_text=state.get('resume_text') or '',
                jd_text=state.get('jd_text') or '',
                last_evaluation={**(state.get('answer_evaluation') or {}), 'follow_up_target': plan.get('target')},
            )
            return {
                'source_count': len(contexts or []),
                'contexts': contexts or [],
                'retrieval_trace': getattr(self, 'last_retrieval_trace', {}) or {},
            }

        result = self._execute_tool('knowledge.hybrid_search', state, handler, {
            'job_position': session.job_position,
            'stage': plan.get('target_stage') or session.current_stage,
            'pending_topics': [plan.get('target_dimension') or plan.get('target_gap') or plan.get('target')],
        })
        output = result.output if result.ok and isinstance(result.output, dict) else {}
        contexts = output.get('contexts') or []
        plan = {**plan, 'use_rag': bool(contexts), 'rag_source_ids': [item.get('chunk_id') for item in contexts[:3] if item.get('chunk_id')]}
        fallback = '' if contexts else (result.error or 'no_approved_rag_context')
        return {
            'rag_context': contexts,
            'retrieval_trace': output.get('retrieval_trace') or {},
            'question_plan': plan,
            'tool_calls': state.get('tool_calls', []),
            'fallback_reason': fallback,
            '_node_status': InterviewAgentNodeRun.Status.SUCCEEDED if contexts else InterviewAgentNodeRun.Status.DEGRADED,
        }

    def _node_skip_rag(self, state: dict) -> dict:
        plan = {**state['question_plan'], 'use_rag': False, 'rag_source_ids': []}
        return {'rag_context': [], 'retrieval_trace': {'skipped': True, 'reason': 'strategy_disabled_retrieval'}, 'question_plan': plan, '_node_status': InterviewAgentNodeRun.Status.SKIPPED}

    def _node_assemble_context(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        context = self.context_budget_manager.compress(
            session=session,
            history=state.get('history') or [],
            rag_context=state.get('rag_context') or [],
            memory_events=state.get('retrieved_memory_events') or [],
            media_context=state.get('media_context') or {},
        )
        context['target_stage'] = state['question_plan'].get('target_stage')
        context['target_dimension'] = state['question_plan'].get('target_dimension')
        context['target_gap'] = state['question_plan'].get('target_gap')
        context['allowed_rag_source_ids'] = state['question_plan'].get('rag_source_ids') or []
        return {'generation_context': context, 'context_budget': {
            'token_budget': context.get('token_budget'),
            'estimated_tokens': context.get('estimated_tokens'),
            'section_tokens': context.get('section_tokens'),
            'dropped': context.get('dropped'),
        }}

    def _node_ingest_generation(self, state: dict) -> dict:
        return {'generated_text': str(state.get('generated_text') or '').strip(), 'generation_attempt': int(state.get('generation_attempt') or 0)}

    def _validate_v2_question(self, state: dict, text: str) -> list[str]:
        session = InterviewSession.objects.get(id=state['session_id'])
        errors = validate_generated_question(
            text,
            state.get('question_plan') or {},
            state.get('rag_context') or [],
            set((session.memory_summary or {}).get('asked_question_signatures') or []),
            self._question_signature,
        )
        if '?' not in text and '？' not in text:
            errors.append('not_a_question')
        if 'AI服务未配置' in text or '调用失败' in text:
            errors.append('service_error_text')
        if any(term in text for term in ('婚育', '民族', '宗教信仰', '政治面貌', '身高体重')):
            errors.append('sensitive_question')
        if any(term in text.lower() for term in ('ignore previous', 'system prompt', '忽略之前', '系统提示词')):
            errors.append('prompt_injection_leak')
        plan = state.get('question_plan') or {}
        if plan.get('target_stage') and plan.get('stage') and plan['target_stage'] != plan['stage']:
            errors.append('stage_mismatch')
        return list(dict.fromkeys(errors))

    def _node_validate(self, state: dict) -> dict:
        result = self._execute_tool(
            'question.validate', state,
            lambda **kwargs: {'errors': self._validate_v2_question(state, kwargs['question_text'])},
            {'question_text': state['generated_text']},
        )
        errors = (result.output or {}).get('errors', []) if result.ok else ['validation_tool_failed']
        return {'validation_errors': errors, 'tool_calls': state.get('tool_calls', [])}

    def _node_repair(self, state: dict) -> dict:
        attempt = int(state.get('generation_attempt') or 0) + 1
        compat = self._adapter_from_dto(state)
        compat.loop_iteration = attempt + 1
        repair_context = {
            **(state.get('generation_context') or {}),
            'repair': {'attempt': attempt, 'validation_errors': state.get('validation_errors') or []},
        }
        setattr(compat, 'generation_context', repair_context)
        repaired = ''.join(self.generate_question_chunks(compat)).strip()
        return {'generated_text': repaired, 'generation_attempt': attempt, 'generation_mode': 'repair'}

    def _safe_question(self, state: dict) -> str:
        plan = state.get('question_plan') or {}
        target = plan.get('target_dimension') or plan.get('target_gap') or '岗位核心能力'
        candidates = [
            f'请围绕{target}，选择一个你亲自参与的真实案例，说明你的关键决策和最终验证结果？',
            f'在你最近的项目中，哪一次经历最能证明你的{target}，你具体做了什么并如何验证结果？',
            f'请用一个未提到过的真实案例说明你在{target}方面的个人贡献和可量化结果？',
        ]
        for candidate in candidates:
            if not self._validate_v2_question(state, candidate):
                return candidate
        sequence = int(state.get('answered_count') or 0) + 1
        return f'作为本场第{sequence}个能力验证问题，请用一个真实案例说明你的个人决策及可验证结果？'

    def _node_safe_fallback(self, state: dict) -> dict:
        text = self._safe_question(state)
        fallback_plan = {**(state.get('question_plan') or {}), 'use_rag': False, 'rag_source_ids': []}
        errors = self._validate_v2_question({**state, 'question_plan': fallback_plan}, text)
        if errors:
            raise RuntimeError(f'safe_fallback_validation_failed:{",".join(errors)}')
        return {
            'generated_text': text,
            'validation_errors': [],
            'generation_mode': 'safe_fallback',
            'question_plan': fallback_plan,
            'rag_context': [],
            'fallback_reason': 'generation_validation_retry_exhausted',
            '_node_status': InterviewAgentNodeRun.Status.DEGRADED,
        }

    def _node_persist(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        plan = state.get('question_plan') or {}
        signature = self._question_signature(state['generated_text'])
        defaults = {
            'question_text': state['generated_text'],
            'rag_context': state.get('rag_context') or [],
            'question_plan': plan,
            'question_signature': signature,
            'target_dimension': plan.get('target_dimension') or '',
            'generation_mode': state.get('generation_mode') or 'model',
            'validation_status': 'validated',
        }
        with transaction.atomic():
            question, _ = InterviewQuestion.objects.get_or_create(
                session=session,
                sequence=int(state.get('answered_count') or 0) + 1,
                defaults=defaults,
            )
            memory = self.remember_generated_question(session.memory_summary or {}, question.question_text)
            session.memory_summary = memory
            session.save(update_fields=['memory_summary', 'updated_at'])
        return {'generated_question_id': question.id, 'generated_text': question.question_text}

    def _node_reflect(self, state: dict) -> dict:
        run = InterviewAgentRun.objects.get(id=state['run_id'])
        run.status = InterviewAgentRun.Status.DEGRADED if state.get('fallback_reason') else InterviewAgentRun.Status.COMPLETED
        run.current_node = 'reflect'
        run.state_snapshot = self._snapshot_state(state)
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'current_node', 'state_snapshot', 'completed_at', 'updated_at'])
        return {'run_completed': True}

    def _node_report_collect(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        turns = []
        for question in session.questions.filter(answered_at__isnull=False).order_by('sequence'):
            evaluation = question.ai_feedback if isinstance(question.ai_feedback, dict) else {}
            evidence = [
                item for item in evaluation.get('evidence_items') or []
                if isinstance(item, dict) and item.get('supported') and item.get('quote')
            ]
            turns.append({
                'sequence': question.sequence,
                'question': question.question_text,
                'answer': question.answer_text,
                'evaluation': evaluation,
                'target_dimension': question.target_dimension,
                'evidence_items': evidence,
                'risk_flags': evaluation.get('risk_flags') or [],
                'rag_source_ids': [item.get('chunk_id') for item in question.rag_context or [] if isinstance(item, dict) and item.get('chunk_id')],
            })
        return {'report_evidence': {
            'turns': turns,
            'coverage_summary': session.coverage_summary or {},
            'session_plan': session.session_plan or {},
            'template_snapshot': session.template_snapshot or {},
        }}

    def _node_report_generate(self, state: dict) -> dict:
        evidence = state['report_evidence']
        turns = evidence.get('turns') or []
        score_summary = summarize_report_scores(turns, evidence.get('session_plan') or {})
        supported = []
        risks = []
        for turn in turns:
            for item in turn.get('evidence_items') or []:
                supported.append(f"第{turn['sequence']}题：{item.get('quote')}")
            for flag in turn.get('risk_flags') or []:
                risks.append(f"第{turn['sequence']}题：{flag}")
        gaps = (evidence.get('coverage_summary') or {}).get('coverage_gaps') or []
        overall_score = score_summary.get('overall_score') or 0
        report = {
            'overall_score': overall_score,
            'ability_scores': score_summary.get('ability_scores') or [],
            'overall_comment': f'本报告基于{len(turns)}轮真实回答、规则/AI双评结果和已验证证据汇总，综合得分为{overall_score}。',
            'strength_analysis': '\n'.join(supported[:5]) if supported else '当前回答中没有达到证据门槛的优势结论。',
            'weakness_analysis': '\n'.join(risks[:5]) if risks else '当前没有可由真实回答证据确认的高风险项。',
            'improvement_suggestions': [f'补充验证能力：{gap}' for gap in gaps[:5]] or ['继续使用具体案例、个人行动和量化结果回答。'],
            'evidence_chain': [
                {
                    'question_sequence': turn['sequence'],
                    'target_dimension': turn.get('target_dimension'),
                    'evidence_items': turn.get('evidence_items') or [],
                    'rag_source_ids': turn.get('rag_source_ids') or [],
                }
                for turn in turns
            ],
            'coverage_summary': evidence.get('coverage_summary') or {},
            'template_snapshot': evidence.get('template_snapshot') or {},
            'report_generation_mode': 'evidence_guarded_composite_v2',
        }
        return {'report_data': report}

    def _node_report_validate(self, state: dict) -> dict:
        report = dict(state['report_data'] or {})
        errors = []
        evidence_chain = report.get('evidence_chain') or []
        supported_count = sum(len(item.get('evidence_items') or []) for item in evidence_chain if isinstance(item, dict))
        if supported_count == 0 and '没有达到证据门槛' not in report.get('strength_analysis', ''):
            report['strength_analysis'] = '当前回答中没有达到证据门槛的优势结论。'
            errors.append('unsupported_strength_removed')
        allowed_rag_ids = {
            str(chunk_id)
            for item in evidence_chain if isinstance(item, dict)
            for chunk_id in item.get('rag_source_ids') or []
        }
        report['rag_source_ids'] = sorted(allowed_rag_ids)
        report['report_validation_errors'] = errors
        return {'report_data': report, 'report_validation_errors': errors, '_node_status': InterviewAgentNodeRun.Status.DEGRADED if errors else InterviewAgentNodeRun.Status.SUCCEEDED}

    def _run_request_hash(self, session, question, answer_text: str, event: str) -> str:
        return self._hash_payload({
            'session_id': str(session.id),
            'question_id': question.id,
            'answer_text': answer_text,
            'answered_at': question.answered_at.isoformat() if question.answered_at else '',
            'event': event,
            'state_schema_version': self.state_schema_version,
        })

    def _get_or_create_run(self, *, session, question, answer_text: str, event: str) -> InterviewAgentRun:
        request_hash = self._run_request_hash(session, question, answer_text, event)
        run, created = InterviewAgentRun.objects.get_or_create(
            session=session,
            event=event,
            request_hash=request_hash,
            defaults={
                'trigger_question': question,
                'engine_name': self.engine_name,
                'status': InterviewAgentRun.Status.RUNNING,
                'state_schema_version': self.state_schema_version,
                'prompt_version': getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1'),
                'model_config_snapshot': (session.session_plan or {}).get('model_config_snapshot', {}),
                'started_at': timezone.now(),
            },
        )
        if not created and run.status == InterviewAgentRun.Status.FAILED:
            run.status = InterviewAgentRun.Status.RUNNING
            run.error_message = ''
            run.started_at = timezone.now()
            run.completed_at = None
            run.save(update_fields=['status', 'error_message', 'started_at', 'completed_at', 'updated_at'])
        return run

    def _initial_state(self, run, *, session, question, user, answer_text, answered_count, history, resume_text, jd_text, media_context, event):
        return {
            'run_id': str(run.id),
            'session_id': str(session.id),
            'question_id': question.id,
            'user_id': user.id,
            'event': event,
            'answer_text': answer_text or '',
            'answered_count': answered_count,
            'history': _json_safe(history or []),
            'resume_text': resume_text or '',
            'jd_text': jd_text or '',
            'media_context': _json_safe(media_context or {}),
            'tool_calls': [],
            'node_order': [],
            'node_outputs': {},
            'generation_attempt': 0,
            **(run.state_snapshot or {}),
        }

    def _invoke_prepare(self, state: dict) -> dict:
        if self._prepare_graph:
            return self._prepare_graph.invoke({'state': state}).get('state', state)
        for name, func in (
            ('load_context', self._node_load_context), ('normalize_input', self._node_normalize_input),
            ('rule_evaluate', self._node_rule_evaluate),
        ):
            state = self._run_node(name, state, func)
        branch = ('ai_evaluate', self._node_ai_evaluate) if state.get('ai_available') else ('rule_degrade', self._node_rule_degrade)
        state = self._run_node(branch[0], state, branch[1])
        for name, func in (
            ('evidence_guard', self._node_evidence_guard), ('update_coverage', self._node_update_coverage_v2),
            ('update_memory', self._node_update_memory_v2), ('recall_memory', self._node_recall_memory),
            ('strategy_plan', self._node_strategy_plan),
        ):
            state = self._run_node(name, state, func)
        branch = ('retrieve', self._node_retrieve_v2) if state.get('retrieval_intent') and not state.get('interview_finished') else ('skip_rag', self._node_skip_rag)
        state = self._run_node(branch[0], state, branch[1])
        return self._run_node('assemble_context', state, self._node_assemble_context)

    def prepare_submit_answer_turn(self, **kwargs) -> InterviewAgentState:
        session = kwargs['session']
        question = kwargs['current_question']
        run = self._get_or_create_run(session=session, question=question, answer_text=kwargs['answer_text'], event='submit_answer_stream')
        state = self._initial_state(
            run, session=session, question=question, user=kwargs['user'], answer_text=kwargs['answer_text'],
            answered_count=kwargs['answered_count'], history=kwargs['history'], resume_text=kwargs.get('resume_text'),
            jd_text=kwargs.get('jd_text'), media_context=kwargs.get('media_context'), event='submit_answer_stream',
        )
        if run.status not in (InterviewAgentRun.Status.WAITING_GENERATION, InterviewAgentRun.Status.COMPLETED, InterviewAgentRun.Status.DEGRADED):
            state = self._invoke_prepare(state)
            run.refresh_from_db()
            run.status = InterviewAgentRun.Status.COMPLETED if state.get('interview_finished') else InterviewAgentRun.Status.WAITING_GENERATION
            run.current_node = 'assemble_context'
            run.state_snapshot = self._snapshot_state(state)
            run.save(update_fields=['status', 'current_node', 'state_snapshot', 'updated_at'])
        compat = self._adapter_from_dto({**state, **(run.state_snapshot or {})})
        if compat.interview_finished and not run.traces.exists():
            self.persist_trace(compat, question=question, extra_outputs={'persist_question': {'skipped': True, 'reason': 'interview_finished'}})
        return compat

    def prepare_regenerate_question_turn(self, **kwargs) -> InterviewAgentState:
        question = kwargs['answered_question']
        run = self._get_or_create_run(session=kwargs['session'], question=question, answer_text=question.answer_text, event='regenerate_next_question')
        state = self._initial_state(
            run, session=kwargs['session'], question=question, user=kwargs['user'], answer_text=question.answer_text,
            answered_count=kwargs['answered_count'], history=kwargs['history'], resume_text=kwargs.get('resume_text'),
            jd_text=kwargs.get('jd_text'), media_context={}, event='regenerate_next_question',
        )
        if run.status not in (InterviewAgentRun.Status.WAITING_GENERATION, InterviewAgentRun.Status.COMPLETED, InterviewAgentRun.Status.DEGRADED):
            # A valid prior evaluation makes coverage idempotent; the same graph can safely resume.
            state = self._invoke_prepare(state)
            run.status = InterviewAgentRun.Status.WAITING_GENERATION
            run.current_node = 'assemble_context'
            run.state_snapshot = self._snapshot_state(state)
            run.save(update_fields=['status', 'current_node', 'state_snapshot', 'updated_at'])
        return self._adapter_from_dto({**state, **(run.state_snapshot or {})})

    def _adapter_from_dto(self, state: dict) -> InterviewAgentState:
        session = InterviewSession.objects.get(id=state['session_id'])
        question = session.questions.get(id=state['question_id'])
        compat = InterviewAgentState(
            session=session,
            user=session.user,
            current_question=question,
            answered_question=question,
            answer_text=state.get('answer_text') or question.answer_text,
            answered_count=int(state.get('answered_count') or 0),
            history=state.get('history') or [],
            resume_text=state.get('resume_text') or '',
            jd_text=state.get('jd_text') or '',
            media_context=state.get('media_context') or {},
            rule_evaluation=state.get('rule_evaluation') or {},
            answer_evaluation=state.get('answer_evaluation') or {},
            coverage_summary=state.get('coverage_summary') or {},
            rag_context=state.get('rag_context') or [],
            retrieval_trace=state.get('retrieval_trace') or {},
            question_plan=state.get('question_plan') or {},
            validation_errors=state.get('validation_errors') or [],
            fallback_reason=state.get('fallback_reason') or '',
            interview_finished=bool(state.get('interview_finished')),
            event=state.get('event') or 'submit_answer_stream',
            node_order=state.get('node_order') or [],
            node_outputs=state.get('node_outputs') or {},
            tool_calls=state.get('tool_calls') or [],
            retrieved_memory_events=state.get('retrieved_memory_events') or [],
            context_budget=state.get('context_budget') or {},
            compressed_context_summary=state.get('generation_context') or {},
            prompt_version=getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1'),
        )
        setattr(compat, 'agent_run_id', state.get('run_id'))
        setattr(compat, 'v2_state', state)
        setattr(compat, 'generation_context', state.get('generation_context') or {})
        return compat

    def generate_question_chunks(self, state: InterviewAgentState):
        yield from generate_next_question_stream(
            job_position=state.session.job_position,
            interview_history=state.history,
            user=state.user,
            total_questions=state.session.question_count,
            resume_text=state.resume_text,
            difficulty=state.session.difficulty,
            current_stage=state.session.current_stage,
            memory_summary=state.session.memory_summary,
            covered_topics=state.session.covered_topics,
            pending_topics=state.session.pending_topics,
            last_evaluation=state.answer_evaluation,
            jd_text=state.jd_text,
            rag_context=state.rag_context,
            generation_context=getattr(state, 'generation_context', {}),
        )

    def finalize_generated_question(self, state: InterviewAgentState, full_question_text: str) -> InterviewQuestion:
        dto = dict(getattr(state, 'v2_state', {}) or {})
        run = InterviewAgentRun.objects.get(id=getattr(state, 'agent_run_id'))
        dto = {**dto, **(run.state_snapshot or {}), 'generated_text': full_question_text, 'generation_attempt': 0}
        if self._finalize_graph:
            dto = self._finalize_graph.invoke({'state': dto}).get('state', dto)
        else:
            dto = self._run_node('ingest_generation', dto, self._node_ingest_generation)
            while True:
                dto = self._run_node('validate', dto, self._node_validate)
                route = self._route_validation({'state': dto})
                if route == 'persist':
                    break
                if route == 'repair':
                    dto = self._run_node('repair', dto, self._node_repair)
                else:
                    dto = self._run_node('safe_fallback', dto, self._node_safe_fallback)
                    break
            dto = self._run_node('persist', dto, self._node_persist)
            dto = self._run_node('reflect', dto, self._node_reflect)
        compat = self._adapter_from_dto(dto)
        compat.generated_question = dto.get('generated_text') or ''
        compat.validation_errors = dto.get('validation_errors') or []
        compat.fallback_reason = dto.get('fallback_reason') or ''
        if not run.traces.exists():
            self.persist_trace(compat, question=state.current_question or state.answered_question)
        return InterviewQuestion.objects.get(id=dto['generated_question_id'])

    def generate_report(self, **kwargs) -> dict:
        session = kwargs.pop('session', None)
        if session is None:
            return super().generate_report(**kwargs)
        last_question = session.questions.filter(answered_at__isnull=False).order_by('-sequence').first()
        request_hash = self._hash_payload({
            'session_id': str(session.id),
            'event': 'finish_report',
            'answered_count': session.questions.filter(answered_at__isnull=False).count(),
            'coverage_summary': session.coverage_summary or {},
            'state_schema_version': self.state_schema_version,
        })
        run, _ = InterviewAgentRun.objects.get_or_create(
            session=session,
            event='finish_report',
            request_hash=request_hash,
            defaults={
                'trigger_question': last_question,
                'engine_name': self.engine_name,
                'status': InterviewAgentRun.Status.RUNNING,
                'state_schema_version': self.state_schema_version,
                'prompt_version': getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1'),
                'started_at': timezone.now(),
            },
        )
        if run.status in (InterviewAgentRun.Status.COMPLETED, InterviewAgentRun.Status.DEGRADED) and (run.state_snapshot or {}).get('report_data'):
            return run.state_snapshot['report_data']
        state = {
            'run_id': str(run.id),
            'session_id': str(session.id),
            'event': 'finish_report',
            'node_order': [],
            'node_outputs': {},
        }
        if self._report_graph:
            state = self._report_graph.invoke({'state': state}).get('state', state)
        else:
            for name, func in (
                ('report_collect', self._node_report_collect),
                ('report_generate', self._node_report_generate),
                ('report_validate', self._node_report_validate),
            ):
                state = self._run_node(name, state, func)
        run.refresh_from_db()
        run.status = InterviewAgentRun.Status.DEGRADED if state.get('report_validation_errors') else InterviewAgentRun.Status.COMPLETED
        run.current_node = 'report_validate'
        run.state_snapshot = self._snapshot_state(state)
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'current_node', 'state_snapshot', 'completed_at', 'updated_at'])
        return state['report_data']
