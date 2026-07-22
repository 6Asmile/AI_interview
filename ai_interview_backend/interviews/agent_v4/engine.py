from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.utils import timezone

from interviews.agent_v3 import CompositeV3InterviewAgentEngine
from interviews.models import InterviewAgentExecution, InterviewAgentRun

from .checkpoint import postgres_checkpointer
from .contracts import AgentEvent, AgentTurnInput, AnswerEvaluation, NextInterviewAction, QuestionPlan
from .state import InterviewGraphEnvelope


class CompositeV4InterviewAgentEngine(CompositeV3InterviewAgentEngine):
    """PostgreSQL-checkpointed V3 behavior with strict boundary contracts."""

    engine_name = 'composite_v4'

    def __init__(self):
        super().__init__()
        self.state_schema_version = 4

    def _graph_state_schema(self):
        return InterviewGraphEnvelope

    def _validate_turn(self, *, run: InterviewAgentRun, session, question, user, answer_text, answered_count, history, resume_text, jd_text, media_context, event):
        return AgentTurnInput.model_validate({
            'session_id': UUID(str(session.id)),
            'question_id': int(question.id),
            'user_id': int(user.id),
            'event': AgentEvent(event),
            'answer_text': str(answer_text or question.answer_text or ''),
            'answered_count': int(answered_count),
            'history': list(history or []),
            'resume_text': str(resume_text or ''),
            'jd_text': str(jd_text or ''),
            'media_context': dict(media_context or {}),
        })

    def _get_or_create_run(self, *, session, question, answer_text: str, event: str) -> InterviewAgentRun:
        run = super()._get_or_create_run(
            session=session,
            question=question,
            answer_text=answer_text,
            event=event,
        )
        with transaction.atomic():
            execution, _ = InterviewAgentExecution.objects.select_for_update().get_or_create(
                session=session,
                event=event,
                idempotency_key=run.request_hash,
                defaults={
                    'trigger_question': question,
                    'legacy_run': run,
                    'thread_id': session.id,
                    'run_id': run.id,
                    'request_hash': run.request_hash,
                    'checkpoint_namespace': f'{event}:{run.id}',
                    'engine_version': self.engine_name,
                    'state_schema_version': self.state_schema_version,
                    'status': InterviewAgentExecution.Status.RUNNING,
                    'started_at': timezone.now(),
                },
            )
            if execution.status == InterviewAgentExecution.Status.FAILED:
                execution.status = InterviewAgentExecution.Status.RUNNING
                execution.error_code = ''
                execution.completed_at = None
                execution.started_at = timezone.now()
                execution.save(update_fields=['status', 'error_code', 'completed_at', 'started_at', 'updated_at'])
        return run

    def _graph_config(self, state: dict, phase: str) -> dict:
        run_id = str(state['run_id'])
        business_thread_id = str(state['session_id'])
        return {
            'configurable': {
                # checkpoint_ns is reserved for compiled subgraphs. The compatibility
                # engine has separate prepare/finalize/report graphs, so each phase
                # receives a durable execution thread while the business thread stays
                # the interview session UUID in Django.
                'thread_id': f'{business_thread_id}.{run_id}.{phase}',
                'checkpoint_ns': '',
            },
            'metadata': {
                'run_id': run_id,
                'session_id': business_thread_id,
                'business_thread_id': business_thread_id,
                'phase': phase,
                'state_schema_version': self.state_schema_version,
            },
        }

    def _invoke_checkpointed(self, *, phase: str, state: dict):
        with postgres_checkpointer() as saver:
            if phase == 'prepare':
                graph = self._compile_prepare_graph_v3(checkpointer=saver)
            elif phase == 'finalize':
                graph = self._compile_finalize_graph(checkpointer=saver)
            elif phase == 'report':
                graph = self._compile_report_graph(checkpointer=saver)
            else:
                raise ValueError(f'unsupported_graph_phase:{phase}')
            config = self._graph_config(state, phase)
            snapshot = graph.get_state(config)
            if snapshot.values:
                if not snapshot.next:
                    return snapshot.values.get('state', state)
                payload = None
            else:
                payload = {'state': state}
            return graph.invoke(payload, config=config).get('state', state)

    def _invoke_prepare(self, state: dict) -> dict:
        return self._invoke_checkpointed(phase='prepare', state=state)

    def _invoke_graph(self, phase: str, graph, state: dict) -> dict:
        return self._invoke_checkpointed(phase=phase, state=state)

    def _node_evidence_guard(self, state: dict) -> dict:
        delta = super()._node_evidence_guard(state)
        evaluation = dict(delta.get('answer_evaluation') or {})
        evidence_items = []
        contract_input_errors = []

        def numeric(value, field_name, default=0.0):
            try:
                return float(value if value is not None else default)
            except (TypeError, ValueError):
                contract_input_errors.append(field_name)
                return float(default)

        for item in evaluation.get('evidence_items') or []:
            if not isinstance(item, dict) or not str(item.get('quote') or '').strip():
                continue
            source = item.get('source') if item.get('source') in ('candidate_answer', 'rag') else 'candidate_answer'
            if source == 'rag' and not item.get('chunk_id'):
                contract_input_errors.append('evidence_items.chunk_id')
                continue
            evidence_items.append({
                'source': source,
                'quote': str(item['quote'])[:2000],
                'supported': bool(item.get('supported')),
                'chunk_id': str(item['chunk_id']) if source == 'rag' and item.get('chunk_id') else None,
            })
        fallback_reason = str(
            evaluation.get('fallback_reason')
            or evaluation.get('degraded_reason')
            or state.get('fallback_reason')
            or ''
        )[:200]
        raw_contract = {
            'evaluation_mode': evaluation.get('evaluation_mode') or 'rule_only_degraded',
            'rule_score': numeric(evaluation.get('rule_score'), 'rule_score'),
            'ai_score': numeric(evaluation.get('ai_score'), 'ai_score') if evaluation.get('ai_score') is not None else None,
            'final_score': numeric(evaluation.get('final_score') or evaluation.get('quality_score'), 'final_score'),
            'confidence': numeric(evaluation.get('confidence'), 'confidence'),
            'evidence_items': evidence_items[:30],
            'risk_flags': [str(item)[:200] for item in (evaluation.get('risk_flags') or [])[:30]],
            'fallback_reason': fallback_reason,
        }
        try:
            if contract_input_errors:
                raise ValueError(','.join(contract_input_errors))
            validated = AnswerEvaluation.model_validate(raw_contract)
        except (TypeError, ValueError):
            rule_score = max(0.0, min(100.0, numeric(evaluation.get('rule_score'), 'rule_score')))
            validated = AnswerEvaluation.model_validate({
                'evaluation_mode': 'rule_only_degraded',
                'rule_score': rule_score,
                'ai_score': None,
                'final_score': rule_score,
                'confidence': max(0.0, min(1.0, numeric(evaluation.get('confidence'), 'confidence'))),
                'evidence_items': [
                    item for item in evidence_items
                    if item['supported'] and (item['source'] != 'rag' or item['chunk_id'])
                ][:30],
                'risk_flags': ['structured_output_validation_failed'],
                'fallback_reason': 'structured_output_validation_failed',
            })
            evaluation['degraded_reason'] = 'structured_output_validation_failed'
            delta['fallback_reason'] = 'structured_output_validation_failed'
        evaluation.update(validated.model_dump(mode='json'))
        evaluation['structured_contract'] = 'answer_evaluation_v1'
        delta['answer_evaluation'] = evaluation
        return delta

    def _node_plan_transition(self, state: dict) -> dict:
        delta = super()._node_plan_transition(state)
        plan = dict(delta.get('question_plan') or state.get('question_plan') or {})
        use_rag = bool(plan.get('use_rag'))
        plan_contract_error = ''
        try:
            next_action = NextInterviewAction(plan.get('next_action') or NextInterviewAction.PROBE)
        except (TypeError, ValueError):
            next_action = NextInterviewAction.PROBE
            plan_contract_error = 'next_action'
        raw_contract = {
            'target_stage': str(plan.get('target_stage') or plan.get('stage') or 'technical_deep_dive'),
            'target_dimension': str(
                plan.get('target_dimension') or plan.get('target_gap') or state.get('current_topic') or '岗位核心能力'
            ),
            'target_gap': str(plan.get('target_gap') or '')[:500],
            'difficulty': plan.get('difficulty') or 'medium',
            'next_action': next_action,
            'use_rag': use_rag,
            'rag_source_ids': list(plan.get('rag_source_ids') or []) if use_rag else [],
        }
        try:
            if plan_contract_error:
                raise ValueError(plan_contract_error)
            validated = QuestionPlan.model_validate(raw_contract)
        except (TypeError, ValueError):
            validated = QuestionPlan.model_validate({
                'target_stage': str(plan.get('stage') or 'technical_deep_dive'),
                'target_dimension': str(state.get('current_topic') or '岗位核心能力'),
                'target_gap': '',
                'difficulty': 'medium',
                'next_action': NextInterviewAction.PROBE,
                'use_rag': False,
                'rag_source_ids': [],
            })
            delta['fallback_reason'] = 'question_plan_validation_failed'
        plan.update(validated.model_dump(mode='json'))
        plan['structured_contract'] = 'question_plan_v1'
        delta['question_plan'] = plan
        return delta

    def _initial_state(self, run, **kwargs):
        payload = self._validate_turn(run=run, **kwargs)
        state = super()._initial_state(run, **kwargs)
        state['schema_version'] = self.state_schema_version
        state['thread_id'] = str(payload.session_id)
        return state

    def _sync_execution(self, run_id, *, status, fallback_reason='', error_code=''):
        durable_status_map = {
            InterviewAgentExecution.Status.RUNNING: InterviewAgentExecution.Status.EVALUATING,
            InterviewAgentExecution.Status.WAITING: InterviewAgentExecution.Status.EVALUATED,
            InterviewAgentExecution.Status.DEGRADED: InterviewAgentExecution.Status.COMPLETED,
            InterviewAgentExecution.Status.FAILED: InterviewAgentExecution.Status.FAILED_RETRYABLE,
        }
        status = durable_status_map.get(status, status)
        updates = {
            'status': status,
            'fallback_reason': str(fallback_reason or '')[:200],
            'error_code': str(error_code or '')[:100],
        }
        if status in (
            InterviewAgentExecution.Status.COMPLETED,
            InterviewAgentExecution.Status.FAILED_TERMINAL,
        ):
            updates['completed_at'] = timezone.now()
        active_statuses = (
            InterviewAgentExecution.Status.ACCEPTED,
            InterviewAgentExecution.Status.ANSWER_PERSISTED,
            InterviewAgentExecution.Status.EVALUATING,
            InterviewAgentExecution.Status.EVALUATED,
            InterviewAgentExecution.Status.GENERATING,
            InterviewAgentExecution.Status.PENDING,
            InterviewAgentExecution.Status.RUNNING,
            InterviewAgentExecution.Status.WAITING,
        )
        InterviewAgentExecution.objects.filter(run_id=run_id, status__in=active_statuses).update(
            **updates,
            updated_at=timezone.now(),
        )

    def prepare_submit_answer_turn(self, **kwargs):
        try:
            state = super().prepare_submit_answer_turn(**kwargs)
            status = InterviewAgentExecution.Status.COMPLETED if state.interview_finished else InterviewAgentExecution.Status.WAITING
            self._sync_execution(state.agent_run_id, status=status, fallback_reason=state.fallback_reason)
            return state
        except Exception as exc:
            question = kwargs['current_question']
            request_hash = self._run_request_hash(
                kwargs['session'],
                question,
                kwargs['answer_text'],
                'submit_answer_stream',
            )
            run = InterviewAgentRun.objects.filter(
                session=kwargs['session'],
                event='submit_answer_stream',
                request_hash=request_hash,
            ).first()
            if run:
                self._sync_execution(run.id, status=InterviewAgentExecution.Status.FAILED, error_code=type(exc).__name__)
            raise

    def prepare_regenerate_question_turn(self, **kwargs):
        state = super().prepare_regenerate_question_turn(**kwargs)
        self._sync_execution(state.agent_run_id, status=InterviewAgentExecution.Status.WAITING, fallback_reason=state.fallback_reason)
        return state

    def finalize_generated_question(self, state, full_question_text):
        try:
            question = super().finalize_generated_question(state, full_question_text)
            final_status = (
                InterviewAgentExecution.Status.DEGRADED
                if state.fallback_reason else InterviewAgentExecution.Status.COMPLETED
            )
            self._sync_execution(state.agent_run_id, status=final_status, fallback_reason=state.fallback_reason)
            return question
        except Exception as exc:
            self._sync_execution(state.agent_run_id, status=InterviewAgentExecution.Status.FAILED, error_code=type(exc).__name__)
            raise
