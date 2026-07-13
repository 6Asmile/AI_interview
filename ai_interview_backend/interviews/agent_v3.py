from __future__ import annotations

import re
from statistics import median

from django.utils import timezone

from .agent_v2 import (
    SUBAGENT_CONTRACTS,
    CompositeV2InterviewAgentEngine,
    InterviewSubAgent,
)
from .models import InterviewQuestion, InterviewSession


V3_CONTRACTS = {
    'evaluate_evidence': InterviewSubAgent(
        'EvaluationAgent', ('answer_evaluation', 'answer_text'),
        ('answer_evidence_profile', 'answer_state'),
    ),
    'update_topic_state': InterviewSubAgent(
        'MemoryAgent', ('answer_text', 'current_question_plan'),
        ('topic_stack', 'current_topic', 'followup_depth'),
    ),
    'estimate_ability_confidence': InterviewSubAgent(
        'EvaluationAgent', ('coverage_summary', 'answer_evidence_profile'),
        ('ability_confidence',),
    ),
    'decide_termination': InterviewSubAgent(
        'StrategyAgent', ('answered_count', 'coverage_summary', 'answer_state'),
        ('termination_decision', 'interview_finished'),
    ),
    'select_next_action': InterviewSubAgent(
        'StrategyAgent', ('answer_state', 'termination_decision', 'followup_depth'),
        ('next_action', 'question_plan', 'retrieval_intent'),
    ),
    'plan_transition': InterviewSubAgent(
        'ConversationAgent', ('next_action', 'question_plan', 'answer_text'),
        ('dialogue_turn_plan', 'question_plan'),
    ),
    'update_memory_v3': InterviewSubAgent(
        'MemoryAgent', ('topic_stack', 'question_plan', 'termination_decision'),
        ('session_snapshot',),
    ),
}
SUBAGENT_CONTRACTS.update(V3_CONTRACTS)


DEFAULT_STYLE_PROFILES = {
    'relaxed': {
        'warmth': 0.9, 'strictness': 0.25, 'pace': 'steady', 'challenge_rate': 0.35,
        'max_followups_per_topic': 2, 'allow_interrupt': False,
        'acknowledgement_style': 'warm_neutral', 'transition_style': 'conversational',
    },
    'strict': {
        'warmth': 0.35, 'strictness': 0.9, 'pace': 'fast', 'challenge_rate': 0.85,
        'max_followups_per_topic': 3, 'allow_interrupt': True,
        'acknowledgement_style': 'brief_neutral', 'transition_style': 'direct',
    },
    'project_with_fundamentals': {
        'warmth': 0.65, 'strictness': 0.6, 'pace': 'steady', 'challenge_rate': 0.65,
        'max_followups_per_topic': 3, 'allow_interrupt': False,
        'acknowledgement_style': 'evidence_based', 'transition_style': 'topic_bridge',
    },
}

MODE_STAGE_GRAPHS = {
    'fundamentals': ['opening', 'self_intro', 'fundamentals_probe', 'role_specific', 'system_design', 'behavioral'],
    'project_deep_dive': ['opening', 'self_intro', 'project_anchor', 'project_deep_dive', 'role_specific', 'behavioral'],
    'system_design': ['opening', 'self_intro', 'project_anchor', 'role_specific', 'system_design', 'behavioral'],
    'behavioral': ['opening', 'self_intro', 'project_anchor', 'behavioral'],
    'project_with_fundamentals': ['opening', 'self_intro', 'project_anchor', 'project_deep_dive', 'fundamentals_probe', 'role_specific', 'system_design', 'behavioral'],
    'relaxed': ['opening', 'self_intro', 'project_anchor', 'project_deep_dive', 'role_specific', 'behavioral'],
    'strict': ['opening', 'self_intro', 'project_anchor', 'project_deep_dive', 'fundamentals_probe', 'system_design', 'behavioral'],
    'structured': ['opening', 'self_intro', 'project_anchor', 'project_deep_dive', 'fundamentals_probe', 'role_specific', 'system_design', 'behavioral'],
}


class CompositeV3InterviewAgentEngine(CompositeV2InterviewAgentEngine):
    """Time-and-coverage adaptive interview with evidence-grounded dialogue turns."""

    engine_name = 'composite_v3'

    def __init__(self):
        super().__init__()
        self.state_schema_version = 3
        self._prepare_graph = self._compile_prepare_graph_v3()

    def _compile_prepare_graph_v3(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None
        graph = StateGraph(dict)
        nodes = (
            ('load_context', self._node_load_context),
            ('normalize_input', self._node_normalize_input),
            ('rule_evaluate', self._node_rule_evaluate),
            ('ai_evaluate', self._node_ai_evaluate),
            ('rule_degrade', self._node_rule_degrade),
            ('evidence_guard', self._node_evidence_guard),
            ('update_coverage', self._node_update_coverage_v2),
            ('evaluate_evidence', self._node_evaluate_evidence),
            ('update_topic_state', self._node_update_topic_state),
            ('estimate_ability_confidence', self._node_estimate_ability_confidence),
            ('decide_termination', self._node_decide_termination),
            ('recall_memory', self._node_recall_memory),
            ('select_next_action', self._node_select_next_action),
            ('plan_transition', self._node_plan_transition),
            ('update_memory_v3', self._node_update_memory_v3),
            ('retrieve', self._node_retrieve_v2),
            ('skip_rag', self._node_skip_rag),
            ('assemble_context', self._node_assemble_context_v3),
        )
        for name, func in nodes:
            graph.add_node(name, self._wrap_node(name, func))
        graph.set_entry_point('load_context')
        graph.add_edge('load_context', 'normalize_input')
        graph.add_edge('normalize_input', 'rule_evaluate')
        graph.add_conditional_edges('rule_evaluate', self._route_ai, {'ai': 'ai_evaluate', 'degrade': 'rule_degrade'})
        graph.add_edge('ai_evaluate', 'evidence_guard')
        graph.add_edge('rule_degrade', 'evidence_guard')
        graph.add_edge('evidence_guard', 'update_coverage')
        graph.add_edge('update_coverage', 'evaluate_evidence')
        graph.add_edge('evaluate_evidence', 'update_topic_state')
        graph.add_edge('update_topic_state', 'estimate_ability_confidence')
        graph.add_edge('estimate_ability_confidence', 'decide_termination')
        graph.add_edge('decide_termination', 'recall_memory')
        graph.add_edge('recall_memory', 'select_next_action')
        graph.add_edge('select_next_action', 'plan_transition')
        graph.add_edge('plan_transition', 'update_memory_v3')
        graph.add_conditional_edges('update_memory_v3', self._route_retrieval, {'retrieve': 'retrieve', 'skip': 'skip_rag'})
        graph.add_edge('retrieve', 'assemble_context')
        graph.add_edge('skip_rag', 'assemble_context')
        graph.add_edge('assemble_context', END)
        return graph.compile()

    @staticmethod
    def _plain_text(value: str) -> str:
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value or '')).strip()

    def _node_evaluate_evidence(self, state: dict) -> dict:
        answer = self._plain_text(state.get('answer_text') or '')
        evaluation = state.get('answer_evaluation') or {}
        final_score = int(evaluation.get('final_score') or 0)
        evidence = [
            item for item in evaluation.get('evidence_items') or []
            if isinstance(item, dict) and item.get('supported') and item.get('quote')
        ]
        has_number = bool(re.search(r'\d+|百分之|提升|降低|qps|ms|秒|分钟', answer.lower()))
        has_ownership = bool(re.search(r'我(负责|主导|设计|实现|推动|排查)|个人(负责|贡献)', answer))
        has_tradeoff = any(word in answer for word in ('权衡', '取舍', '代价', '边界', '风险', '对比'))
        contradiction = any(
            '矛盾' in str(flag) or '不一致' in str(flag)
            for flag in evaluation.get('risk_flags') or []
        )
        confidence = float(evaluation.get('confidence') or (0.8 if len(answer) >= 80 else 0.55))
        profile = {
            'correctness': int(evaluation.get('relevance_score') or final_score),
            'specificity': min(100, 25 + len(answer) // 2 + (15 if evidence else 0)),
            'ownership': 85 if has_ownership else 40,
            'technical_depth': int(evaluation.get('depth_score') or final_score),
            'tradeoff_quality': 85 if has_tradeoff else 40,
            'result_evidence': min(100, 35 + (30 if has_number else 0) + (20 if evidence else 0)),
            'consistency': 25 if contradiction else 85,
            'confidence': confidence,
            'supported_evidence_count': len(evidence),
        }
        if contradiction:
            answer_state = 'contradictory'
        elif len(answer) < 24 or final_score < 45:
            answer_state = 'insufficient'
        elif confidence < 0.6:
            answer_state = 'ambiguous'
        elif final_score < 70 or not evidence:
            answer_state = 'partial'
        elif final_score >= 85 and has_tradeoff and (has_number or len(evidence) >= 2):
            answer_state = 'strong'
        else:
            answer_state = 'solid'
        evaluation['answer_evidence_profile'] = profile
        evaluation['answer_state'] = answer_state
        question = None
        if state.get('session_id') and state.get('question_id'):
            question = InterviewQuestion.objects.get(
                session_id=state['session_id'],
                id=state['question_id'],
            )
        if question is not None:
            question.ai_feedback = evaluation
            question.save(update_fields=['ai_feedback', 'evaluated_at'])
        return {
            'answer_evidence_profile': profile,
            'answer_state': answer_state,
            'answer_evaluation': evaluation,
        }

    def _node_update_topic_state(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        memory = session.memory_summary or {}
        prior_plan = state.get('current_question_plan') or {}
        answer = self._plain_text(state.get('answer_text') or '')
        known_topics = ('Redis', 'MySQL', 'Kafka', 'RabbitMQ', 'Docker', 'Kubernetes', 'Django', 'Vue', 'RAG', 'Agent', 'LangGraph', '微服务', '缓存', '数据库')
        mentioned = next((topic for topic in known_topics if topic.lower() in answer.lower()), '')
        current = mentioned or prior_plan.get('topic_id') or memory.get('current_topic') or prior_plan.get('target_dimension') or '岗位核心能力'
        prior_topic = prior_plan.get('topic_id') or memory.get('current_topic') or ''
        depth = int(prior_plan.get('followup_depth') or memory.get('followup_depth') or 0)
        depth = depth + 1 if prior_topic and current == prior_topic else 0
        stack = list(memory.get('topic_stack') or [])
        if current and (not stack or stack[-1].get('topic_id') != current):
            stack.append({'topic_id': current, 'parent_topic_id': prior_topic, 'status': 'active'})
        return {'topic_stack': stack[-8:], 'current_topic': current, 'followup_depth': depth}

    def _node_estimate_ability_confidence(self, state: dict) -> dict:
        session_plan = (state.get('session_snapshot') or {}).get('session_plan') or {}
        coverage = (state.get('coverage_summary') or {}).get('coverage') or {}
        requirements = session_plan.get('coverage_requirements') or {}
        evidence_confidence = float((state.get('answer_evidence_profile') or {}).get('confidence') or 0)
        confidence = {}
        for key, requirement in requirements.items():
            needed = max(1, int(requirement.get('min_coverage') or 1))
            ratio = min(1.0, float(coverage.get(key, 0)) / needed)
            confidence[key] = round(ratio * evidence_confidence, 3)
        return {'ability_confidence': confidence}

    def _node_decide_termination(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        policy = (session.session_plan or {}).get('termination_policy') or {}
        elapsed = max(0, int((timezone.now() - session.started_at).total_seconds())) if session.started_at else 0
        target = int(policy.get('target_duration_minutes') or session.target_duration_minutes or 30) * 60
        minimum = int(policy.get('min_duration_minutes') or 20) * 60
        hard_max = int(policy.get('hard_max_duration_minutes') or 45) * 60
        min_turns = int(policy.get('min_turns') or 5)
        max_turns = int(policy.get('max_turns') or 18)
        answered = int(state.get('answered_count') or 0)
        gaps = list((state.get('coverage_summary') or {}).get('coverage_gaps') or [])
        requirements = (session.session_plan or {}).get('coverage_requirements') or {}
        weights = [float(item.get('weight') or 0) for item in requirements.values()] or [0]
        threshold = median(weights)
        mandatory = [gap for gap in gaps if float((requirements.get(gap) or {}).get('weight') or 0) >= threshold]
        optional = [gap for gap in gaps if gap not in mandatory]
        memory = session.memory_summary or {}
        candidate_asked = bool(memory.get('candidate_question_asked'))
        hard_stop = elapsed >= hard_max or answered >= max_turns
        coverage_ready = not mandatory
        ready_for_candidate = answered >= min_turns and elapsed >= minimum and (coverage_ready or elapsed >= target)
        finish = hard_stop or (ready_for_candidate and candidate_asked)
        reason = (
            'hard_limit_reached' if hard_stop else
            'coverage_and_time_satisfied' if finish else
            'invite_candidate_question' if ready_for_candidate else
            'continue_coverage'
        )
        decision = {
            'continue_interview': not finish,
            'reason': reason,
            'elapsed_seconds': elapsed,
            'remaining_seconds': max(0, target - elapsed),
            'mandatory_gaps': mandatory,
            'optional_gaps': optional,
            'next_stage': InterviewSession.InterviewStage.CLOSING if finish else session.current_stage,
            'invite_candidate_question': bool(ready_for_candidate and not candidate_asked and not hard_stop),
        }
        return {'termination_decision': decision, 'interview_finished': finish, 'elapsed_seconds': elapsed, 'remaining_seconds': decision['remaining_seconds']}

    def _node_select_next_action(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        decision = state['termination_decision']
        answer_state = state['answer_state']
        depth = int(state.get('followup_depth') or 0)
        style = {**DEFAULT_STYLE_PROFILES.get(session.interview_mode, DEFAULT_STYLE_PROFILES['project_with_fundamentals']), **((session.session_plan or {}).get('style_profile') or {})}
        max_followups = int(style.get('max_followups_per_topic') or 3)
        if not decision['continue_interview']:
            action = 'END'
        elif decision.get('invite_candidate_question'):
            action = 'CANDIDATE_QUESTION'
        elif answer_state == 'contradictory':
            action = 'VERIFY'
        elif answer_state in ('insufficient', 'ambiguous'):
            action = 'CLARIFY' if depth < 2 else 'ASK_NEW'
        elif answer_state == 'partial':
            action = 'PROBE' if depth < max_followups else 'ASK_NEW'
        elif answer_state == 'strong':
            action = 'CHALLENGE' if depth < max_followups else 'TRANSFER'
        else:
            action = 'PROBE' if depth < max_followups else 'ASK_NEW'
        gaps = decision.get('mandatory_gaps') or decision.get('optional_gaps') or []
        current_plan = state.get('current_question_plan') or {}
        target_dimension = current_plan.get('target_dimension') or (gaps[0] if gaps else '')
        if action in ('ASK_NEW', 'TRANSFER') and gaps:
            target_dimension = gaps[0]
        target_stage = session.current_stage
        if action == 'CANDIDATE_QUESTION':
            target_stage = InterviewSession.InterviewStage.CANDIDATE_QUESTIONS
        elif action == 'END':
            target_stage = InterviewSession.InterviewStage.CLOSING
        else:
            graph = MODE_STAGE_GRAPHS.get(session.interview_mode, MODE_STAGE_GRAPHS['project_with_fundamentals'])
            if session.current_stage == InterviewSession.InterviewStage.OPENING:
                target_stage = graph[1]
            elif action in ('ASK_NEW', 'TRANSFER') and session.current_stage in graph:
                index = graph.index(session.current_stage)
                target_stage = graph[min(index + 1, len(graph) - 1)]
        retrieval_intent = action in ('PROBE', 'CHALLENGE', 'TRANSFER', 'ASK_NEW') and target_stage != InterviewSession.InterviewStage.CANDIDATE_QUESTIONS
        plan = {
            'stage': session.current_stage,
            'target_stage': target_stage,
            'target_dimension': target_dimension,
            'target_gap': gaps[0] if gaps else '',
            'target': (state.get('answer_evaluation') or {}).get('follow_up_target') or target_dimension or state.get('current_topic'),
            'difficulty': (session.memory_summary or {}).get('adaptive_difficulty') or session.difficulty,
            'next_action': action,
            'topic_id': state.get('current_topic') or '',
            'parent_topic_id': (current_plan.get('topic_id') or ''),
            'followup_depth': depth,
            'answer_state': answer_state,
            'retrieval_intent': retrieval_intent,
            'use_rag': False,
            'rag_source_ids': [],
            'style_profile': style,
            'termination_reason': decision.get('reason'),
        }
        return {'next_action': action, 'question_plan': plan, 'retrieval_intent': retrieval_intent}

    def _answer_reference(self, answer: str, topic: str) -> str:
        text = self._plain_text(answer)
        if topic and topic in text:
            return topic
        clauses = [item.strip() for item in re.split(r'[，。；！？!?]', text) if len(item.strip()) >= 4]
        return (clauses[0][:28] if clauses else '')

    def _node_plan_transition(self, state: dict) -> dict:
        plan = dict(state['question_plan'])
        action = state['next_action']
        reference = self._answer_reference(state.get('answer_text') or '', plan.get('topic_id') or '')
        dialogue_act = {
            'CLARIFY': 'clarify', 'VERIFY': 'verify', 'PROBE': 'probe', 'CHALLENGE': 'challenge',
            'TRANSFER': 'transfer', 'ASK_NEW': 'transition', 'CANDIDATE_QUESTION': 'candidate_question', 'END': 'closing',
        }.get(action, 'probe')
        transition_reason = {
            'CLARIFY': '补充上一轮尚不明确的事实和个人行动',
            'VERIFY': '核对上一轮回答中的关键结论',
            'PROBE': '沿上一轮提到的内容继续下钻',
            'CHALLENGE': '验证方案边界、取舍和异常场景',
            'TRANSFER': '验证能力能否迁移到新的场景',
            'ASK_NEW': '当前话题已获得足够信息，切换到下一能力',
            'CANDIDATE_QUESTION': '主要能力验证已接近完成，进入候选人反问',
            'END': '本场面试达到结束条件',
        }.get(action, '')
        turn = {
            'dialogue_act': dialogue_act,
            'acknowledgement': 'neutral_evidence_based',
            'answer_reference': reference,
            'transition_reason': transition_reason,
            'question_intent': plan.get('target') or plan.get('target_dimension') or '',
            'question_text': '',
            'tts_style': {
                'pace': (plan.get('style_profile') or {}).get('pace', 'steady'),
                'strictness': (plan.get('style_profile') or {}).get('strictness', 0.6),
            },
        }
        plan['dialogue_act'] = dialogue_act
        plan['answer_reference'] = reference
        plan['transition_reason'] = transition_reason
        return {'dialogue_turn_plan': turn, 'question_plan': plan}

    def _node_update_memory_v3(self, state: dict) -> dict:
        session = InterviewSession.objects.get(id=state['session_id'])
        plan = state['question_plan']
        memory = {
            **(session.memory_summary or {}),
            'topic_stack': state.get('topic_stack') or [],
            'current_topic': state.get('current_topic') or '',
            'followup_depth': state.get('followup_depth') or 0,
            'answer_state': state.get('answer_state'),
            'answer_evidence_profile': state.get('answer_evidence_profile') or {},
            'ability_confidence': state.get('ability_confidence') or {},
            'stage_plan': plan,
            'termination_decision': state.get('termination_decision') or {},
        }
        if plan.get('next_action') == 'CANDIDATE_QUESTION':
            memory['candidate_question_asked'] = True
        session.current_stage = plan.get('target_stage') or session.current_stage
        session.memory_summary = memory
        session.save(update_fields=['current_stage', 'memory_summary', 'updated_at'])
        snapshot = {**state['session_snapshot'], 'current_stage': session.current_stage, 'memory_summary': memory}
        return {'session_snapshot': snapshot}

    def _node_assemble_context_v3(self, state: dict) -> dict:
        delta = super()._node_assemble_context(state)
        context = delta['generation_context']
        context['next_action'] = state.get('next_action')
        context['answer_evidence_profile'] = state.get('answer_evidence_profile') or {}
        context['dialogue_turn_plan'] = state.get('dialogue_turn_plan') or {}
        context['topic_stack'] = state.get('topic_stack') or []
        context['termination_decision'] = state.get('termination_decision') or {}
        return {**delta, 'generation_context': context}

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
            ('evaluate_evidence', self._node_evaluate_evidence), ('update_topic_state', self._node_update_topic_state),
            ('estimate_ability_confidence', self._node_estimate_ability_confidence),
            ('decide_termination', self._node_decide_termination), ('recall_memory', self._node_recall_memory),
            ('select_next_action', self._node_select_next_action), ('plan_transition', self._node_plan_transition),
            ('update_memory_v3', self._node_update_memory_v3),
        ):
            state = self._run_node(name, state, func)
        branch = ('retrieve', self._node_retrieve_v2) if state.get('retrieval_intent') and not state.get('interview_finished') else ('skip_rag', self._node_skip_rag)
        state = self._run_node(branch[0], state, branch[1])
        return self._run_node('assemble_context', state, self._node_assemble_context_v3)

    def _snapshot_state(self, state: dict) -> dict:
        snapshot = super()._snapshot_state(state)
        for key in (
            'answer_evidence_profile', 'answer_state', 'topic_stack', 'current_topic',
            'followup_depth', 'ability_confidence', 'next_action', 'dialogue_turn_plan',
            'elapsed_seconds', 'remaining_seconds', 'termination_decision',
        ):
            if key in state:
                snapshot[key] = state[key]
        return snapshot

    def _validate_v2_question(self, state: dict, text: str) -> list[str]:
        errors = super()._validate_v2_question(state, text)
        plan = state.get('question_plan') or {}
        session = InterviewSession.objects.get(id=state['session_id'])
        graph = MODE_STAGE_GRAPHS.get(session.interview_mode, MODE_STAGE_GRAPHS['project_with_fundamentals'])
        source_stage = plan.get('stage')
        target_stage = plan.get('target_stage')
        valid_transition = source_stage == target_stage
        if source_stage in graph and target_stage in graph:
            valid_transition = abs(graph.index(target_stage) - graph.index(source_stage)) <= 1
        if valid_transition or plan.get('next_action') == 'CANDIDATE_QUESTION':
            errors = [error for error in errors if error != 'stage_mismatch']
        reference = plan.get('answer_reference') or ''
        if reference and plan.get('next_action') in ('CLARIFY', 'VERIFY', 'PROBE', 'CHALLENGE') and reference not in text:
            errors.append('missing_answer_bridge')
        if any(term in text for term in ('你的回答很优秀', '回答得非常全面', '你的回答很差', '得分')):
            errors.append('evaluation_leak_or_false_praise')
        return list(dict.fromkeys(errors))

    def _route_validation(self, payload: dict) -> str:
        state = payload.get('state') or {}
        errors = set(state.get('validation_errors') or [])
        if not errors:
            return 'persist'
        # Structural failures are safer and much faster to repair deterministically.
        # Re-prompting the model for these errors can add tens of seconds while still
        # producing another multi-question turn with no grounded answer bridge.
        if {'multiple_questions', 'missing_answer_bridge'}.issubset(errors):
            return 'fallback'
        return super()._route_validation(payload)

    def _safe_question(self, state: dict) -> str:
        plan = state.get('question_plan') or {}
        action = plan.get('next_action')
        reference = plan.get('answer_reference') or plan.get('topic_id') or ''
        target = plan.get('target_dimension') or plan.get('target_gap') or '岗位核心能力'
        if action == 'CANDIDATE_QUESTION':
            return '主要问题先到这里。在结束前，你有什么希望进一步了解或需要我说明的吗？'
        prefix = f'你刚才提到“{reference}”，' if reference else ''
        questions = {
            'CLARIFY': f'{prefix}请补充一个具体场景，说明你当时承担的职责和最终结果？',
            'VERIFY': f'{prefix}我想确认这个关键点：你个人实际负责的部分是什么？',
            'PROBE': f'{prefix}沿着这个点继续看，你当时最关键的技术决策是什么，如何验证它有效？',
            'CHALLENGE': f'{prefix}如果关键依赖失效或数据规模扩大十倍，你会如何调整这个方案？',
            'TRANSFER': f'换一个场景验证一下：面对更严格的可用性要求，你会如何运用{target}解决问题？',
            'ASK_NEW': f'我们换到{target}。请选择一个真实案例，说明你的关键决策和验证结果？',
        }
        return questions.get(action) or super()._safe_question(state)

    def _node_safe_fallback(self, state: dict) -> dict:
        delta = super()._node_safe_fallback(state)
        original_errors = set(state.get('validation_errors') or [])
        if {'multiple_questions', 'missing_answer_bridge'}.issubset(original_errors):
            delta['fallback_reason'] = 'structural_validation_fallback'
        return delta

    def _node_report_generate(self, state: dict) -> dict:
        delta = super()._node_report_generate(state)
        delta['report_data']['report_generation_mode'] = 'evidence_guarded_composite_v3'
        delta['report_data']['termination_decision'] = (
            InterviewSession.objects.get(id=state['session_id']).memory_summary or {}
        ).get('termination_decision') or {}
        return delta
