import logging
import json
import hashlib
import math
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from knowledge.services import RequiredRAGContextUnavailable, search_knowledge_context

from .agent_runtime import (
    AgentHookManager,
    ContextBudgetManager,
    build_default_slash_commands,
    build_default_tool_registry,
    normalize_prompt_version,
)
from .evaluation import (
    combine_rule_and_ai_evaluation,
    rule_evaluate_answer,
    update_session_coverage,
    validate_generated_question,
)
from .models import InterviewAgentMemoryEvent, InterviewAgentToolCall, InterviewAgentTrace, InterviewQuestion
from .ai_services import (
    decide_adaptive_difficulty,
    decide_interview_stage,
    evaluate_answer,
    generate_final_report,
    generate_first_question,
    generate_next_question_stream,
    summarize_perception_data,
    update_interview_memory,
)
from .prompts.profiles import build_interview_prompt_context
from .configuration import assemble_generation_context

logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


@dataclass
class AgentTurn:
    sequence: int
    question: str
    answer: str
    evaluation: dict = field(default_factory=dict)
    perception_summary: dict = field(default_factory=dict)
    rag_context: list = field(default_factory=list)


@dataclass
class AgentToolResult:
    name: str
    ok: bool
    input_summary: dict = field(default_factory=dict)
    output_summary: dict = field(default_factory=dict)
    error: str = ''
    subagent_name: str = ''
    permission_scope: str = ''
    fallback_reason: str = ''
    latency_ms: int | None = None


@dataclass
class InterviewAgentState:
    session: Any
    user: Any
    current_question: Any | None = None
    answered_question: Any | None = None
    answer_text: str = ''
    answered_count: int = 0
    next_sequence: int = 0
    history: list = field(default_factory=list)
    resume_text: str = ''
    jd_text: str = ''
    media_context: dict = field(default_factory=dict)
    environment_context: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    memory_events: list = field(default_factory=list)
    retrieved_memory_events: list = field(default_factory=list)
    ai_evaluation: dict = field(default_factory=dict)
    rule_evaluation: dict = field(default_factory=dict)
    answer_evaluation: dict = field(default_factory=dict)
    perception_summary: dict = field(default_factory=dict)
    coverage_summary: dict = field(default_factory=dict)
    rag_context: list = field(default_factory=list)
    retrieval_trace: dict = field(default_factory=dict)
    question_plan: dict = field(default_factory=dict)
    generated_question: str = ''
    validation_errors: list = field(default_factory=list)
    fallback_reason: str = ''
    interview_finished: bool = False
    event: str = 'submit_answer_stream'
    node_order: list = field(default_factory=list)
    node_outputs: dict = field(default_factory=dict)
    subagent_name: str = ''
    loop_iteration: int = 1
    context_budget: dict = field(default_factory=dict)
    prompt_version: str = ''
    compressed_context_summary: dict = field(default_factory=dict)

    @property
    def feedback_text(self) -> str:
        return self.answer_evaluation.get('feedback', '')


class InterviewAgentEngine:
    """Orchestrates interview agent steps while keeping the public API stable."""

    def build_initial_memory(self, job_position: str, resume_text: str = '', jd_text: str = '') -> tuple[dict, list[str]]:
        raise NotImplementedError

    def generate_first_question(self, *, job_position: str, user, resume_text: str = '', difficulty: str = 'medium', jd_text: str = '', agent_config_snapshot: dict | None = None) -> str:
        raise NotImplementedError

    def evaluate_answer(self, *, job_position: str, question: str, answer: str, user, jd_text: str = '', agent_config_snapshot: dict | None = None, context_envelope: dict | None = None) -> dict:
        raise NotImplementedError

    def summarize_perception(self, analysis_data: list | None) -> dict:
        raise NotImplementedError

    def decide_stage(self, *, next_sequence: int, total_questions: int, has_resume: bool) -> str:
        raise NotImplementedError

    def update_memory(self, *, job_position: str, user, history: list, current_stage: str, resume_text: str = '', jd_text: str = '', agent_config_snapshot: dict | None = None, context_envelope: dict | None = None) -> dict:
        raise NotImplementedError

    def decide_difficulty(self, *, base_difficulty: str, recent_feedback: list, current_stage: str) -> str:
        raise NotImplementedError

    def retrieve_knowledge(self, *, session, history: list, resume_text: str = '', jd_text: str = '', last_evaluation: dict | None = None) -> list[dict]:
        raise NotImplementedError

    def plan_next_question(self, *, session, history: list, rag_context: list, last_evaluation: dict | None = None) -> dict:
        raise NotImplementedError

    def generate_next_question_stream(self, **kwargs):
        raise NotImplementedError

    def generate_report(self, **kwargs) -> dict:
        raise NotImplementedError


class DefaultInterviewAgentEngine(InterviewAgentEngine):
    def _question_signature(self, question_text: str) -> str:
        normalized = re.sub(r'\s+', '', (question_text or '').lower())
        normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', normalized)
        return hashlib.sha256(normalized[:180].encode('utf-8')).hexdigest()[:16]

    def _history_question_signatures(self, history: list) -> list[str]:
        signatures = []
        for item in history or []:
            signature = self._question_signature(item.get('question', ''))
            if signature and signature not in signatures:
                signatures.append(signature)
        return signatures

    def _is_semantic_duplicate_question(self, question_text: str, previous_questions) -> bool:
        def normalize(value: str) -> str:
            normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', (value or '').lower())
            normalized = normalized.replace('怎么', '如何')
            for filler in (
                '请你', '请', '你们', '你的', '你', '在项目中', '项目中', '一下',
                '谈谈', '说说', '说明', '介绍', '是否', '是', '的', '之间', '以及', '和', '与', '及',
            ):
                normalized = normalized.replace(filler, '')
            return normalized

        def intent(value: str) -> str:
            for name, markers in (
                ('why', ('为什么', '原因', '为何')),
                ('how', ('如何', '怎么', '怎样')),
                ('compare', ('区别', '比较', '差异')),
                ('tradeoff', ('取舍', '权衡', '优缺点')),
                ('result', ('结果', '指标', '效果')),
            ):
                if any(marker in value for marker in markers):
                    return name
            return 'general'

        raw_candidate = question_text or ''
        candidate = normalize(raw_candidate)
        if len(candidate) < 8:
            return False
        candidate_bigrams = {candidate[index:index + 2] for index in range(len(candidate) - 1)}
        for previous in previous_questions or []:
            normalized = normalize(previous)
            if len(normalized) < 8:
                continue
            ratio = SequenceMatcher(None, candidate, normalized).ratio()
            previous_bigrams = {normalized[index:index + 2] for index in range(len(normalized) - 1)}
            union = candidate_bigrams | previous_bigrams
            jaccard = len(candidate_bigrams & previous_bigrams) / max(len(union), 1)
            containment = len(candidate_bigrams & previous_bigrams) / max(
                min(len(candidate_bigrams), len(previous_bigrams)), 1,
            )
            same_intent = intent(raw_candidate) == intent(previous or '')
            if ratio >= 0.88 or (same_intent and (jaccard >= 0.68 or containment >= 0.86)):
                return True
        return False

    def _plain_answer_text(self, answer: str) -> str:
        return re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', answer or ''))

    def _summarize_environment_context(self, analysis_data: list | None, media_context: dict | None) -> dict:
        media_context = media_context or {}
        emotion_totals: dict[str, float] = {}
        frame_count = 0
        strongest_frame_scores = []
        for frame in analysis_data or []:
            emotions = frame.get('emotions') if isinstance(frame, dict) else {}
            if not isinstance(emotions, dict):
                continue
            frame_count += 1
            frame_scores = []
            for key, value in emotions.items():
                try:
                    score = float(value)
                    emotion_totals[key] = emotion_totals.get(key, 0.0) + score
                    frame_scores.append(score)
                except (TypeError, ValueError):
                    continue
            if frame_scores:
                strongest_frame_scores.append(max(frame_scores))
        dominant_emotion = ''
        dominant_emotion_score = None
        if emotion_totals:
            dominant_emotion = max(emotion_totals.items(), key=lambda item: item[1])[0]
            dominant_emotion_score = round(emotion_totals[dominant_emotion] / max(frame_count, 1), 4)
        asr_meta = media_context.get('asr_transcript_meta') or {}
        confidence = asr_meta.get('confidence')
        try:
            confidence_value = float(confidence) if confidence not in (None, '') else None
        except (TypeError, ValueError):
            confidence_value = None
        low_confidence = confidence_value is not None and confidence_value < getattr(settings, 'ASR_MIN_CONFIDENCE', 0.65)
        no_visual_frames = frame_count == 0
        weak_visual_signal = bool(
            strongest_frame_scores
            and (sum(strongest_frame_scores) / len(strongest_frame_scores)) < 0.45
        )
        has_audio = bool(media_context.get('audio_artifact_id'))
        audio_without_confidence = has_audio and confidence_value is None
        risk_flags = []
        if no_visual_frames:
            risk_flags.append('no_visual_frames')
        if weak_visual_signal:
            risk_flags.append('weak_visual_signal')
        if low_confidence:
            risk_flags.append('low_asr_confidence')
        if audio_without_confidence:
            risk_flags.append('asr_confidence_missing')

        suggested_action = 'continue'
        if low_confidence:
            suggested_action = 'confirm_transcript_before_deepening'
        elif audio_without_confidence:
            suggested_action = 'ask_candidate_to_confirm_transcript'
        elif no_visual_frames:
            suggested_action = 'ignore_visual_signal'

        visual_signal_quality = 'unavailable' if no_visual_frames else ('weak' if weak_visual_signal else 'normal')
        signal_quality = 'needs_confirmation' if low_confidence or audio_without_confidence else (
            'limited' if no_visual_frames or weak_visual_signal else 'normal'
        )
        return {
            'frame_count': frame_count,
            'dominant_emotion': dominant_emotion,
            'dominant_emotion_score': dominant_emotion_score,
            'has_audio': has_audio,
            'asr_confidence': confidence_value,
            'low_asr_confidence': bool(low_confidence),
            'visual_signal_quality': visual_signal_quality,
            'signal_quality': signal_quality,
            'risk_flags': risk_flags,
            'suggested_action': suggested_action,
            'use_for_scoring': False,
            'scoring_policy': 'environment_signals_are_for_recovery_and_confirmation_only',
        }

    def _coverage_gaps(self, memory_summary: dict, rag_context: list, last_evaluation: dict | None = None) -> list[str]:
        last_evaluation = last_evaluation or {}
        gaps = []
        for item in memory_summary.get('unverified_risks') or memory_summary.get('risks') or []:
            if item and item not in gaps:
                gaps.append(str(item))
        target = last_evaluation.get('follow_up_target')
        if target and target not in gaps:
            gaps.insert(0, target)
        for context in rag_context or []:
            for tag in context.get('ability_tags') or []:
                if tag and tag not in gaps:
                    gaps.append(tag)
        return gaps[:5]

    def load_relevant_memory_events(self, *, session, limit: int = 8) -> list[dict]:
        now = timezone.now()
        candidates = InterviewAgentMemoryEvent.objects.filter(session=session).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).order_by('-importance', '-created_at')[: max(limit * 6, limit)]
        events = [event for event in candidates if self._is_recallable_memory_event(event)]
        events.sort(key=lambda event: self._memory_recall_score(event, now), reverse=True)
        events = events[:limit]
        if events:
            InterviewAgentMemoryEvent.objects.filter(id__in=[event.id for event in events]).update(
                recall_count=F('recall_count') + 1,
                last_recalled_at=now,
            )
        return [
            {
                'id': event.id,
                'event_type': event.event_type,
                'memory_key': event.memory_key,
                'value_summary': event.value_summary,
                'importance': event.importance,
                'recall_score': round(self._memory_recall_score(event, now), 4),
                'source_node': event.source_node,
                'question_id': event.question_id,
                'created_at': event.created_at.isoformat(),
                'expires_at': event.expires_at.isoformat() if event.expires_at else None,
            }
            for event in events
        ]

    def _memory_recall_score(self, event: InterviewAgentMemoryEvent, now=None) -> float:
        now = now or timezone.now()
        age_minutes = max(0.0, (now - event.created_at).total_seconds() / 60)
        half_life = {
            InterviewAgentMemoryEvent.EventType.ENVIRONMENT: 5,
            InterviewAgentMemoryEvent.EventType.OBSERVATION: 20,
            InterviewAgentMemoryEvent.EventType.PLAN: 45,
            InterviewAgentMemoryEvent.EventType.QUESTION: 24 * 60,
            InterviewAgentMemoryEvent.EventType.COVERAGE: 7 * 24 * 60,
        }.get(event.event_type, 60)
        recency = math.pow(0.5, age_minutes / max(half_life, 1))
        return float(event.importance) * 0.8 + recency * 1.2

    def _is_recallable_memory_event(self, event: InterviewAgentMemoryEvent) -> bool:
        value_summary = event.value_summary if isinstance(event.value_summary, dict) else {}
        if event.event_type == InterviewAgentMemoryEvent.EventType.ENVIRONMENT:
            return event.importance >= 4
        if event.event_type == InterviewAgentMemoryEvent.EventType.OBSERVATION:
            if event.memory_key == 'knowledge.hybrid_search':
                return bool(value_summary.get('source_count') or value_summary.get('final_count'))
            return event.importance >= 4
        return True

    def _memory_event_expires_at(self, event_type: str, memory_key: str, value_summary: dict, importance: int):
        value_summary = value_summary or {}
        if event_type == InterviewAgentMemoryEvent.EventType.ENVIRONMENT:
            minutes = 15 if importance >= 4 else 5
            return timezone.now() + timedelta(minutes=minutes)
        if event_type == InterviewAgentMemoryEvent.EventType.OBSERVATION and memory_key == 'knowledge.hybrid_search':
            has_sources = bool(value_summary.get('source_count') or value_summary.get('final_count'))
            return timezone.now() + timedelta(hours=2) if has_sources else timezone.now() + timedelta(minutes=10)
        if event_type == InterviewAgentMemoryEvent.EventType.OBSERVATION:
            return timezone.now() + timedelta(minutes=30)
        if event_type == InterviewAgentMemoryEvent.EventType.PLAN:
            return timezone.now() + timedelta(hours=2)
        return None

    def build_initial_memory(self, job_position: str, resume_text: str = '', jd_text: str = '') -> tuple[dict, list[str]]:
        prompt_context = build_interview_prompt_context(job_position, jd_text=jd_text, resume_text=resume_text)
        pending_topics = ['自我介绍', '岗位匹配度', '代表性项目']
        if prompt_context['profile_key'] == 'ai_application_intern':
            pending_topics = ['自我介绍', '代表性AI项目', 'RAG/Agent/MCP实践']
        elif prompt_context['profile_key'] == 'jd_custom':
            pending_topics = ['自我介绍', 'JD核心职责', 'JD匹配项目/经历']

        memory = {
            'summary': '面试刚开始，第一步先让候选人完成自我介绍，再根据简历和自我介绍选择代表性项目追问。',
            'strengths': [],
            'risks': [],
            'covered_topics': [],
            'pending_topics': pending_topics,
            'question_strategy': '第一题只要求1~3分钟自我介绍，不打断；后续再进入项目深挖。',
            'prompt_profile': prompt_context['profile_key'],
            'prompt_profile_name': prompt_context['profile_name'],
            'jd_text': jd_text,
            'rag_context_count': 0,
            'asked_question_signatures': [],
            'used_knowledge_chunks': [],
            'used_knowledge_groups': [],
            'stage_plan': {},
            'coverage_gaps': [],
        }
        return memory, pending_topics

    def generate_first_question(self, *, job_position: str, user, resume_text: str = '', difficulty: str = 'medium', jd_text: str = '', agent_config_snapshot: dict | None = None) -> str:
        return generate_first_question(
            job_position,
            user,
            resume_text,
            difficulty,
            jd_text=jd_text,
            agent_config_snapshot=agent_config_snapshot,
        )

    def evaluate_answer(self, *, job_position: str, question: str, answer: str, user, jd_text: str = '', agent_config_snapshot: dict | None = None, context_envelope: dict | None = None) -> dict:
        return evaluate_answer(
            job_position,
            question,
            answer,
            user,
            jd_text=jd_text,
            agent_config_snapshot=agent_config_snapshot,
            context_envelope=context_envelope,
        )

    def summarize_perception(self, analysis_data: list | None) -> dict:
        return summarize_perception_data(analysis_data)

    def decide_stage(self, *, next_sequence: int, total_questions: int, has_resume: bool) -> str:
        return decide_interview_stage(next_sequence, total_questions, has_resume)

    def update_memory(self, *, job_position: str, user, history: list, current_stage: str, resume_text: str = '', jd_text: str = '', agent_config_snapshot: dict | None = None, context_envelope: dict | None = None) -> dict:
        return update_interview_memory(
            job_position,
            user,
            history,
            current_stage,
            resume_text,
            jd_text=jd_text,
            agent_config_snapshot=agent_config_snapshot,
            context_envelope=context_envelope,
        )

    def decide_difficulty(self, *, base_difficulty: str, recent_feedback: list, current_stage: str) -> str:
        return decide_adaptive_difficulty(base_difficulty, recent_feedback, current_stage)

    def retrieve_knowledge(self, *, session, history: list, resume_text: str = '', jd_text: str = '', last_evaluation: dict | None = None) -> list[dict]:
        memory = session.memory_summary or {}
        used_chunk_ids = list(memory.get('used_knowledge_chunks') or [])
        used_group_ids = set(memory.get('used_knowledge_groups') or [])
        for question in session.questions.exclude(rag_context__isnull=True):
            rag_context = question.rag_context if isinstance(question.rag_context, list) else []
            used_chunk_ids.extend(item.get('chunk_id') for item in rag_context if isinstance(item, dict))
            used_group_ids.update(
                item.get('semantic_group_id') for item in rag_context
                if isinstance(item, dict) and item.get('semantic_group_id')
            )

        try:
            result = search_knowledge_context(
                job_position=session.job_position,
                user=session.user,
                current_stage=session.current_stage,
                pending_topics=session.pending_topics or (session.memory_summary or {}).get('pending_topics', []),
                last_evaluation=last_evaluation or {},
                jd_text=jd_text,
                difficulty=(session.memory_summary or {}).get('adaptive_difficulty') or session.difficulty,
                exclude_chunk_ids=used_chunk_ids,
                limit=4,
                return_trace=True,
                agent_config_snapshot=session.agent_config_snapshot or {},
            )
            if isinstance(result, dict):
                self.last_retrieval_trace = result.get('retrieval_trace') or {}
                self.last_retrieval_explanation = result.get('retrieval_explanation') or {}
                contexts = []
                turn_groups = set()
                for item in result.get('contexts') or []:
                    group_id = item.get('semantic_group_id')
                    if group_id and (group_id in used_group_ids or group_id in turn_groups):
                        continue
                    contexts.append(item)
                    if group_id:
                        turn_groups.add(group_id)
                    if len(contexts) >= 4:
                        break
                if getattr(session.template, 'require_rag', False) and not contexts:
                    raise RequiredRAGContextUnavailable(
                        self.last_retrieval_trace.get('fallback_reason')
                        or 'required_rag_context_unavailable'
                    )
                return contexts
            self.last_retrieval_trace = {}
            self.last_retrieval_explanation = {}
            return result
        except RequiredRAGContextUnavailable:
            raise
        except Exception as exc:
            logger.warning('Knowledge retrieval failed; continuing without RAG context: %s', exc)
            self.last_retrieval_trace = {'fallback_reason': str(exc)}
            self.last_retrieval_explanation = {'fallback_reason': str(exc), 'steps': []}
            if getattr(session.template, 'require_rag', False):
                raise RequiredRAGContextUnavailable(str(exc)) from exc
            return []

    def _build_knowledge_tool_result(self, state: InterviewAgentState) -> AgentToolResult:
        retrieval_trace = state.retrieval_trace or {}
        retrieval_explanation = getattr(self, 'last_retrieval_explanation', {}) or {}
        fallback_reason = retrieval_explanation.get('fallback_reason') or retrieval_trace.get('fallback_reason') or ''
        source_count = len(state.rag_context or [])
        if not source_count and not fallback_reason:
            fallback_reason = 'no_approved_rag_context'
        return AgentToolResult(
            name='knowledge.hybrid_search',
            ok=bool(source_count),
            input_summary={
                'job_position': state.session.job_position,
                'stage': state.session.current_stage,
                'pending_topics': state.session.pending_topics,
                'difficulty': (state.session.memory_summary or {}).get('adaptive_difficulty') or state.session.difficulty,
                'exclude_used_chunks': len((state.session.memory_summary or {}).get('used_knowledge_chunks') or []),
            },
            output_summary={
                'source_count': source_count,
                'retrieval_trace': retrieval_trace,
                'retrieval_explanation': retrieval_explanation,
                'candidate_summary': retrieval_explanation.get('candidate_summary') or {},
                'filters': retrieval_explanation.get('filters') or {},
                'fallback_reason': fallback_reason,
                'sources': [
                    {
                        'document_id': item.get('document_id'),
                        'chunk_id': item.get('chunk_id'),
                        'title': item.get('title'),
                        'visibility': item.get('visibility'),
                        'ability_tags': item.get('ability_tags'),
                        'score': item.get('score'),
                        'rerank_score': item.get('rerank_score'),
                    }
                    for item in (state.rag_context or [])[:6]
                    if isinstance(item, dict)
                ],
            },
            error='' if source_count else fallback_reason,
        )

    def plan_next_question(self, *, session, history: list, rag_context: list, last_evaluation: dict | None = None) -> dict:
        memory = session.memory_summary or {}
        retrieved_memory = memory.get('retrieved_memory_events') or []
        coverage_gaps = self._coverage_gaps(memory, rag_context, last_evaluation)
        plan_gaps = ((session.session_plan or {}).get('coverage_gaps') or []) if hasattr(session, 'session_plan') else []
        dimensions = ((session.session_plan or {}).get('dimensions') or []) if hasattr(session, 'session_plan') else []
        dimension_keys = [item.get('key') for item in dimensions if item.get('key')]
        target_dimension = (
            plan_gaps[0] if plan_gaps else
            (coverage_gaps[0] if coverage_gaps and coverage_gaps[0] in dimension_keys else '') or
            (dimension_keys[0] if dimension_keys else '')
        )
        latest_answer = self._plain_answer_text((history or [{}])[-1].get('answer', '') if history else '')
        is_short_answer = bool(history) and len(latest_answer) < 24
        environment_context = memory.get('environment_context') or {}
        needs_audio_confirmation = bool(environment_context.get('low_asr_confidence'))
        environment_policy = {
            'use_for_scoring': bool(environment_context.get('use_for_scoring', False)),
            'suggested_action': environment_context.get('suggested_action') or 'continue',
            'risk_flags': environment_context.get('risk_flags') or [],
        }
        next_sequence = len(history or []) + 1
        is_final_question = next_sequence >= getattr(session, 'question_count', 999)
        if needs_audio_confirmation:
            target = '上一轮语音转写置信度偏低，先请候选人确认或复述关键结论，再继续追问具体证据。'
        elif is_short_answer:
            target = '候选人上一题回答过短，先要求其补充具体背景、个人行动、结果和量化证据。'
        elif is_final_question and coverage_gaps:
            target = f'结束前补问最关键未验证风险：{coverage_gaps[0]}。要求候选人用一个具体案例收束说明。'
        else:
            memory_target = ''
            for event in retrieved_memory:
                summary = event.get('value_summary') or {}
                candidate = summary.get('target') or summary.get('target_gap')
                if candidate:
                    memory_target = str(candidate)
                    break
            target = (
                (last_evaluation or {}).get('follow_up_target')
                or (coverage_gaps[0] if coverage_gaps else '')
                or (f'结合历史记忆继续验证：{memory_target}' if memory_target else '')
                or memory.get('question_strategy')
                or '结合候选人上一题回答继续追问具体案例、个人贡献和量化结果。'
            )
        used_chunks = list(dict.fromkeys(
            list(memory.get('used_knowledge_chunks') or []) +
            [item.get('chunk_id') for item in rag_context or [] if item.get('chunk_id')]
        ))
        used_groups = list(dict.fromkeys(
            list(memory.get('used_knowledge_groups') or []) +
            [item.get('semantic_group_id') for item in rag_context or [] if item.get('semantic_group_id')]
        ))
        signatures = list(dict.fromkeys(
            list(memory.get('asked_question_signatures') or []) +
            self._history_question_signatures(history)
        ))
        plan = {
            'stage': session.current_stage,
            'difficulty': memory.get('adaptive_difficulty') or session.difficulty,
            'target': target,
            'use_rag': bool(rag_context),
            'last_tool_observation': memory.get('last_tool_observation') or {},
            'target_dimension': target_dimension,
            'target_stage': session.current_stage,
            'target_gap': plan_gaps[0] if plan_gaps else (coverage_gaps[0] if coverage_gaps else ''),
            'rag_source_ids': [item.get('chunk_id') for item in (rag_context or [])[:3] if item.get('chunk_id')],
            'rag_sources': [
                {'title': item.get('title'), 'chunk_id': item.get('chunk_id'), 'visibility': item.get('visibility')}
                for item in (rag_context or [])[:3]
            ],
            'memory_recall': [
                {
                    'event_type': event.get('event_type'),
                    'memory_key': event.get('memory_key'),
                    'importance': event.get('importance'),
                    'source_node': event.get('source_node'),
                    'value_summary': event.get('value_summary'),
                }
                for event in retrieved_memory[:5]
            ],
            'avoid_question_signatures': signatures[-8:],
            'coverage_gaps': coverage_gaps,
            'needs_audio_confirmation': needs_audio_confirmation,
            'environment_policy': environment_policy,
            'short_answer_clarification': is_short_answer,
            'final_gap_priority': bool(is_final_question and coverage_gaps),
        }
        memory.update({
            'stage_plan': plan,
            'coverage_gaps': coverage_gaps,
            'used_knowledge_chunks': used_chunks[-30:],
            'used_knowledge_groups': used_groups[-30:],
            'asked_question_signatures': signatures[-30:],
            'rag_context_count': len(rag_context or []),
            'last_rag_sources': plan['rag_sources'],
            'last_memory_recall': plan['memory_recall'],
            'environment_policy': environment_policy,
        })
        return plan

    def remember_generated_question(self, memory_summary: dict, question_text: str) -> dict:
        memory_summary = memory_summary or {}
        signature = self._question_signature(question_text)
        signatures = list(memory_summary.get('asked_question_signatures') or [])
        if signature and signature not in signatures:
            signatures.append(signature)
        memory_summary['asked_question_signatures'] = signatures[-30:]
        return memory_summary

    def remember_tool_observation(self, memory_summary: dict, tool_result: dict) -> dict:
        memory_summary = memory_summary or {}
        output_summary = tool_result.get('output_summary') or {}
        retrieval_trace = output_summary.get('retrieval_trace') or {}
        retrieval_explanation = output_summary.get('retrieval_explanation') or {}
        candidate_summary = retrieval_explanation.get('candidate_summary') or output_summary.get('candidate_summary') or {}
        observation = {
            'name': tool_result.get('name', ''),
            'ok': bool(tool_result.get('ok')),
            'source_count': output_summary.get('source_count', 0),
            'error': tool_result.get('error', ''),
            'vector_count': retrieval_trace.get('vector_count', 0),
            'keyword_count': retrieval_trace.get('keyword_count', 0),
            'rrf_count': retrieval_trace.get('rrf_count', 0),
            'filtered_count': retrieval_trace.get('filtered_count', 0),
            'rerank_used': retrieval_trace.get('rerank_used', False),
            'final_count': candidate_summary.get('final_count', output_summary.get('source_count', 0)),
            'fallback_reason': retrieval_explanation.get('fallback_reason') or output_summary.get('fallback_reason') or '',
            'filter_reasons': retrieval_explanation.get('filters') or output_summary.get('filters') or {},
            'step_statuses': {
                step.get('name'): step.get('status')
                for step in retrieval_explanation.get('steps') or []
                if isinstance(step, dict) and step.get('name')
            },
            'created_at': timezone.now().isoformat(),
        }
        observations = list(memory_summary.get('tool_observations') or [])
        observations.append(observation)
        memory_summary['tool_observations'] = observations[-20:]
        memory_summary['last_tool_observation'] = observation
        return memory_summary

    def _mark_node(self, state: InterviewAgentState, name: str, output: dict | None = None) -> None:
        state.node_order.append(name)
        state.node_outputs[name] = output or {}

    def _record_memory_event(
        self,
        state: InterviewAgentState,
        *,
        event_type: str,
        memory_key: str,
        value_summary: dict,
        importance: int = 1,
        source_node: str = '',
    ) -> None:
        normalized_importance = max(1, min(int(importance or 1), 5))
        canonical = json.dumps({
            'event_type': event_type,
            'memory_key': memory_key,
            'value_summary': _json_safe(value_summary or {}),
        }, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        dedup_key = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        if any(event.get('dedup_key') == dedup_key for event in state.memory_events):
            return
        state.memory_events.append({
            'event_type': event_type,
            'memory_key': memory_key,
            'dedup_key': dedup_key,
            'value_summary': value_summary or {},
            'importance': normalized_importance,
            'source_node': source_node,
            'expires_at': self._memory_event_expires_at(event_type, memory_key, value_summary or {}, normalized_importance),
        })

    def _node_load_session_state(self, state: InterviewAgentState) -> InterviewAgentState:
        state.next_sequence = state.answered_count + 1
        self._mark_node(state, 'load_session_state', {
            'stage': state.session.current_stage,
            'pending_topics': state.session.pending_topics,
            'covered_topics': state.session.covered_topics,
            'next_sequence': state.next_sequence,
        })
        return state

    def _node_normalize_multimodal_input(self, state: InterviewAgentState) -> InterviewAgentState:
        media_context = state.media_context or {}
        state.media_context = {
            'audio_artifact_id': media_context.get('audio_artifact_id') or '',
            'asr_transcript_meta': media_context.get('asr_transcript_meta') or {},
            'has_audio': bool(media_context.get('audio_artifact_id')),
        }
        self._mark_node(state, 'normalize_multimodal_input', state.media_context)
        return state

    def _node_summarize_environment_context(self, state: InterviewAgentState) -> InterviewAgentState:
        state.environment_context = self._summarize_environment_context(
            state.current_question.analysis_data if state.current_question else [],
            state.media_context,
        )
        environment_importance = 1
        if state.environment_context.get('low_asr_confidence') or state.environment_context.get('asr_confidence') is None and state.environment_context.get('has_audio'):
            environment_importance = 4
        elif state.environment_context.get('risk_flags'):
            environment_importance = 2
        self._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.ENVIRONMENT,
            memory_key='environment_context',
            value_summary=state.environment_context,
            importance=environment_importance,
            source_node='summarize_environment_context',
        )
        self._mark_node(state, 'summarize_environment_context', state.environment_context)
        return state

    def _node_evaluate_answer_rule(self, state: InterviewAgentState) -> InterviewAgentState:
        state.rule_evaluation = rule_evaluate_answer(
            question=state.current_question.question_text,
            answer=state.answer_text,
            session_plan=state.session.session_plan,
        )
        self._mark_node(state, 'evaluate_answer_rule', {
            'rule_score': state.rule_evaluation.get('rule_score'),
            'risk_flags': state.rule_evaluation.get('risk_flags', []),
        })
        return state

    def _node_evaluate_answer_ai(self, state: InterviewAgentState) -> InterviewAgentState:
        context_envelope = assemble_generation_context(
            session=state.session,
            history=state.history,
            rag_context=[],
            memory_events=state.retrieved_memory_events,
            media_context=state.media_context,
            task_context={'task': 'answer_evaluation'},
            current_question=state.current_question.question_text,
            candidate_answer=state.answer_text,
            resume_text=state.resume_text,
            jd_text=state.jd_text,
        )
        state.ai_evaluation = self.evaluate_answer(
            job_position=state.session.job_position,
            question=state.current_question.question_text,
            answer=state.answer_text,
            user=state.user,
            jd_text=state.jd_text,
            agent_config_snapshot=state.session.agent_config_snapshot,
            context_envelope=context_envelope,
        )
        state.answer_evaluation = combine_rule_and_ai_evaluation(state.rule_evaluation, state.ai_evaluation)
        self._mark_node(state, 'evaluate_answer_ai', {
            'ai_score': state.answer_evaluation.get('ai_score'),
            'final_score': state.answer_evaluation.get('final_score'),
            'evaluation_mode': state.answer_evaluation.get('evaluation_mode'),
            'degraded_reason': state.answer_evaluation.get('degraded_reason'),
        })
        return state

    def _node_update_coverage(self, state: InterviewAgentState) -> InterviewAgentState:
        state.current_question.ai_feedback = state.answer_evaluation
        state.current_question.evaluated_at = timezone.now()
        state.current_question.save(update_fields=['ai_feedback', 'evaluated_at'])
        state.coverage_summary = update_session_coverage(state.session, state.answer_evaluation)
        state.perception_summary = self.summarize_perception(state.current_question.analysis_data)
        self._mark_node(state, 'update_coverage', state.coverage_summary)
        return state

    def _node_update_memory(self, state: InterviewAgentState) -> InterviewAgentState:
        if state.answered_count >= state.session.question_count:
            state.interview_finished = True
            self._mark_node(state, 'update_memory', {'skipped': True, 'reason': 'interview_finished'})
            return state
        next_stage = self.decide_stage(
            next_sequence=state.answered_count + 1,
            total_questions=state.session.question_count,
            has_resume=bool(state.resume_text),
        )
        memory_summary = self.update_memory(
            job_position=state.session.job_position,
            user=state.user,
            history=state.history,
            current_stage=next_stage,
            resume_text=state.resume_text,
            jd_text=state.jd_text,
            agent_config_snapshot=state.session.agent_config_snapshot,
            context_envelope=assemble_generation_context(
                session=state.session,
                history=state.history,
                rag_context=[],
                memory_events=state.retrieved_memory_events,
                media_context=state.media_context,
                task_context={'task': 'memory_summary', 'next_stage': next_stage},
                current_question=state.current_question.question_text,
                candidate_answer=state.answer_text,
                resume_text=state.resume_text,
                jd_text=state.jd_text,
            ),
        )
        recent_feedback = [
            item.get('evaluation')
            for item in state.history
            if isinstance(item.get('evaluation'), dict)
        ]
        adaptive_difficulty = self.decide_difficulty(
            base_difficulty=state.session.difficulty,
            recent_feedback=recent_feedback,
            current_stage=next_stage,
        )
        memory_summary['adaptive_difficulty'] = adaptive_difficulty
        memory_summary['last_quality_score'] = state.answer_evaluation.get('quality_score')
        memory_summary['last_answer_level'] = state.answer_evaluation.get('answer_level')
        memory_summary['follow_up_target'] = state.answer_evaluation.get('follow_up_target')
        memory_summary['should_escalate'] = state.answer_evaluation.get('should_escalate')
        memory_summary['jd_text'] = state.jd_text
        memory_summary['environment_context'] = state.environment_context
        memory_summary['environment_risks'] = state.environment_context.get('risk_flags') or []
        memory_summary['environment_scoring_policy'] = state.environment_context.get('scoring_policy')
        state.session.current_stage = next_stage
        state.session.memory_summary = memory_summary
        state.session.covered_topics = memory_summary.get('covered_topics', [])
        state.session.pending_topics = memory_summary.get('pending_topics', [])
        state.session.perception_summary = state.perception_summary
        state.session.save(update_fields=[
            'current_stage',
            'memory_summary',
            'covered_topics',
            'pending_topics',
            'perception_summary',
            'updated_at',
        ])
        self._mark_node(state, 'update_memory', {
            'stage': next_stage,
            'adaptive_difficulty': adaptive_difficulty,
            'pending_topics': state.session.pending_topics,
        })
        return state

    def _node_retrieve_knowledge(self, state: InterviewAgentState) -> InterviewAgentState:
        if state.interview_finished:
            self._mark_node(state, 'retrieve_knowledge', {'skipped': True})
            return state
        state.rag_context = self.retrieve_knowledge(
            session=state.session,
            history=state.history,
            resume_text=state.resume_text,
            jd_text=state.jd_text,
            last_evaluation=state.answer_evaluation,
        )
        state.retrieval_trace = getattr(self, 'last_retrieval_trace', {}) or {}
        state.tool_calls.append(self._build_knowledge_tool_result(state).__dict__)
        state.session.memory_summary = self.remember_tool_observation(
            state.session.memory_summary or {},
            state.tool_calls[-1],
        )
        self._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.OBSERVATION,
            memory_key='knowledge.hybrid_search',
            value_summary=(state.session.memory_summary or {}).get('last_tool_observation') or {},
            importance=4 if state.rag_context else 2,
            source_node='retrieve_knowledge',
        )
        self._mark_node(state, 'retrieve_knowledge', {
            'source_count': len(state.rag_context or []),
            'retrieval_trace': state.retrieval_trace,
            'retrieval_explanation': getattr(self, 'last_retrieval_explanation', {}) or {},
            'tool_call': state.tool_calls[-1] if state.tool_calls else {},
            'sources': [
                {
                    'document_id': item.get('document_id'),
                    'chunk_id': item.get('chunk_id'),
                    'title': item.get('title'),
                    'visibility': item.get('visibility'),
                    'ability_tags': item.get('ability_tags'),
                    'score': item.get('score'),
                }
                for item in (state.rag_context or [])[:6]
                if isinstance(item, dict)
            ],
        })
        return state

    def _node_load_long_term_memory(self, state: InterviewAgentState) -> InterviewAgentState:
        if state.interview_finished:
            self._mark_node(state, 'load_long_term_memory', {'skipped': True})
            return state
        state.retrieved_memory_events = self.load_relevant_memory_events(session=state.session)
        state.session.memory_summary = {
            **(state.session.memory_summary or {}),
            'retrieved_memory_events': state.retrieved_memory_events,
        }
        state.session.save(update_fields=['memory_summary', 'updated_at'])
        self._mark_node(state, 'load_long_term_memory', {
            'event_count': len(state.retrieved_memory_events),
            'events': [
                {
                    'event_type': event.get('event_type'),
                    'memory_key': event.get('memory_key'),
                    'importance': event.get('importance'),
                    'source_node': event.get('source_node'),
                }
                for event in state.retrieved_memory_events[:6]
            ],
        })
        return state

    def _node_plan_next_question(self, state: InterviewAgentState) -> InterviewAgentState:
        if state.interview_finished:
            state.question_plan = {'stage': state.session.current_stage, 'target': 'finish_interview'}
            self._mark_node(state, 'plan_next_question', state.question_plan)
            return state
        state.question_plan = self.plan_next_question(
            session=state.session,
            history=state.history,
            rag_context=state.rag_context,
            last_evaluation=state.answer_evaluation,
        )
        state.session.memory_summary = {
            **(state.session.memory_summary or {}),
            'question_strategy': state.question_plan.get('target') or (state.session.memory_summary or {}).get('question_strategy'),
            'last_tool_observation': (state.session.memory_summary or {}).get('last_tool_observation') or {},
        }
        state.session.save(update_fields=['memory_summary', 'updated_at'])
        self._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.PLAN,
            memory_key='question_plan',
            value_summary={
                'stage': state.question_plan.get('stage'),
                'target_dimension': state.question_plan.get('target_dimension'),
                'target_gap': state.question_plan.get('target_gap'),
                'use_rag': state.question_plan.get('use_rag'),
                'needs_audio_confirmation': state.question_plan.get('needs_audio_confirmation'),
                'target': state.question_plan.get('target'),
            },
            importance=4,
            source_node='plan_next_question',
        )
        self._mark_node(state, 'plan_next_question', state.question_plan)
        return state

    def prepare_submit_answer_turn(
        self,
        *,
        session,
        current_question,
        answer_text: str,
        user,
        answered_count: int,
        history: list,
        resume_text: str = '',
        jd_text: str = '',
        media_context: dict | None = None,
    ) -> InterviewAgentState:
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=current_question,
            answer_text=answer_text,
            answered_count=answered_count,
            history=history,
            resume_text=resume_text or '',
            jd_text=jd_text or '',
            media_context=media_context or {},
            event='submit_answer_stream',
        )
        for node in [
            self._node_load_session_state,
            self._node_normalize_multimodal_input,
            self._node_summarize_environment_context,
            self._node_evaluate_answer_rule,
            self._node_evaluate_answer_ai,
            self._node_update_coverage,
            self._node_update_memory,
            self._node_load_long_term_memory,
            self._node_retrieve_knowledge,
            self._node_plan_next_question,
        ]:
            state = node(state)
        if state.interview_finished:
            state.fallback_reason = 'final_question_no_generation'
            self.persist_trace(state, extra_outputs={'persist_question': {'skipped': True, 'reason': 'interview_finished'}})
        return state

    def prepare_regenerate_question_turn(
        self,
        *,
        session,
        answered_question,
        user,
        answered_count: int,
        history: list,
        resume_text: str = '',
        jd_text: str = '',
    ) -> InterviewAgentState:
        state = InterviewAgentState(
            session=session,
            user=user,
            answered_question=answered_question,
            current_question=answered_question,
            answer_text=answered_question.answer_text,
            answered_count=answered_count,
            next_sequence=answered_count + 1,
            history=history,
            resume_text=resume_text or '',
            jd_text=jd_text or '',
            answer_evaluation=answered_question.ai_feedback if isinstance(answered_question.ai_feedback, dict) else {},
            event='regenerate_next_question',
        )
        self._node_load_session_state(state)
        self._node_normalize_multimodal_input(state)
        self._node_summarize_environment_context(state)
        self._mark_node(state, 'evaluate_answer_rule', {'skipped': True, 'reason': 'already_evaluated'})
        self._mark_node(state, 'evaluate_answer_ai', {'skipped': True, 'reason': 'already_evaluated'})
        self._mark_node(state, 'update_coverage', {'skipped': True, 'reason': 'already_evaluated'})
        self._mark_node(state, 'update_memory', {'skipped': True, 'stage': session.current_stage})
        self._node_load_long_term_memory(state)
        self._node_retrieve_knowledge(state)
        self._node_plan_next_question(state)
        return state

    def generate_question_chunks(self, state: InterviewAgentState):
        context_envelope = (
            getattr(state, 'generation_context', None)
            or state.compressed_context_summary
            or assemble_generation_context(
                session=state.session,
                history=state.history,
                rag_context=state.rag_context,
                memory_events=state.retrieved_memory_events,
                media_context=state.media_context,
                task_context=state.question_plan or {},
                current_question=state.current_question.question_text if state.current_question else '',
                candidate_answer=state.answer_text,
                resume_text=state.resume_text,
                jd_text=state.jd_text,
            )
        )
        yield from self.generate_next_question_stream(
            user=state.user,
            agent_config_snapshot=state.session.agent_config_snapshot,
            context_envelope=context_envelope,
        )

    def finalize_generated_question(self, state: InterviewAgentState, full_question_text: str) -> InterviewQuestion:
        full_question_text = (full_question_text or '').strip()
        if not full_question_text:
            full_question_text = '请结合一个具体项目，谈谈你做过的最有价值的一次技术决策。'
            state.fallback_reason = 'empty_generation'
        self._mark_node(state, 'generate_question', {'question_text': full_question_text})
        existing_signatures = set((state.session.memory_summary or {}).get('asked_question_signatures') or [])
        state.validation_errors = validate_generated_question(
            full_question_text,
            state.question_plan,
            state.rag_context,
            existing_signatures,
            self._question_signature,
        )
        previous_questions = state.session.questions.values_list('question_text', flat=True)
        if self._is_semantic_duplicate_question(full_question_text, previous_questions):
            state.validation_errors.append('semantic_duplicate_question')
        state.validation_errors = list(dict.fromkeys(state.validation_errors))
        if 'duplicate_question' in state.validation_errors or 'semantic_duplicate_question' in state.validation_errors:
            fallback_target = (state.session.memory_summary or {}).get('stage_plan', {}).get('target')
            full_question_text = f"{fallback_target or '围绕上一题回答中最关键的能力缺口'}，请补充一个更具体的真实案例，并说明你的个人贡献和结果验证。"
            state.fallback_reason = 'duplicate_question_signature'
        elif 'multiple_questions' in state.validation_errors:
            fallback_target = state.question_plan.get('target_gap') or state.question_plan.get('target_dimension') or state.question_plan.get('target')
            full_question_text = f"请只围绕{fallback_target or '上一题回答中最关键的能力缺口'}，用一个真实案例说明你的个人贡献和可验证结果。"
            state.fallback_reason = 'multiple_questions_collapsed'
        elif state.validation_errors and not state.fallback_reason:
            state.fallback_reason = ','.join(state.validation_errors[:3])
        self._mark_node(state, 'validate_question', {
            'validation_errors': state.validation_errors,
            'fallback_reason': state.fallback_reason,
        })

        next_question, created = InterviewQuestion.objects.get_or_create(
            session=state.session,
            sequence=state.answered_count + 1,
            defaults={'question_text': full_question_text, 'rag_context': state.rag_context},
        )
        state.generated_question = next_question.question_text
        self._mark_node(state, 'persist_question', {
            'question_id': next_question.id,
            'sequence': next_question.sequence,
            'created': created,
        })
        self._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.QUESTION,
            memory_key=f'question:{next_question.sequence}',
            value_summary={
                'question_id': next_question.id,
                'sequence': next_question.sequence,
                'question_text': next_question.question_text,
                'target_dimension': state.question_plan.get('target_dimension'),
                'rag_source_ids': state.question_plan.get('rag_source_ids', []),
                'validation_errors': state.validation_errors,
            },
            importance=5,
            source_node='persist_question',
        )
        state.session.memory_summary = self.remember_generated_question(state.session.memory_summary, next_question.question_text)
        state.session.save(update_fields=['memory_summary', 'updated_at'])
        self.persist_trace(
            state,
            question=state.current_question or state.answered_question,
        )
        return next_question

    def persist_trace(self, state: InterviewAgentState, question=None, extra_outputs: dict | None = None) -> None:
        node_outputs = dict(state.node_outputs)
        if extra_outputs:
            node_outputs.update(extra_outputs)
        node_outputs = _json_safe(node_outputs)
        fallback_reason = state.fallback_reason or ('' if state.rag_context else 'no_approved_rag_context')
        trace = InterviewAgentTrace.objects.create(
            agent_run_id=getattr(state, 'agent_run_id', None),
            session=state.session,
            question=question or state.current_question or state.answered_question,
            event=state.event,
            stage=state.session.current_stage or '',
            node_outputs=node_outputs,
            answer_evaluation=_json_safe(state.answer_evaluation or {}),
            rag_context=_json_safe(state.rag_context or []),
            question_plan=_json_safe(state.question_plan or {}),
            generated_question=state.generated_question or '',
            fallback_reason=fallback_reason,
            input_hash=hashlib.sha256(json.dumps(node_outputs, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest(),
            output_summary=_json_safe({
                'generated_question_length': len(state.generated_question or ''),
                'final_score': (state.answer_evaluation or {}).get('final_score'),
                'evaluation_mode': (state.answer_evaluation or {}).get('evaluation_mode'),
                'node_order': state.node_order,
                'media_context': state.media_context,
                'environment_context': state.environment_context,
                'tool_calls': state.tool_calls,
                'memory_events': state.memory_events,
                'retrieved_memory_events': state.retrieved_memory_events,
            }),
            validation_errors=_json_safe(state.validation_errors or []),
            model_config_snapshot=_json_safe((state.session.session_plan or {}).get('model_config_snapshot', {})),
            subagent_name=state.subagent_name or '',
            loop_iteration=state.loop_iteration or 1,
            context_budget=_json_safe(state.context_budget or {}),
            prompt_version=state.prompt_version or '',
            compressed_context_summary=_json_safe(state.compressed_context_summary or {}),
        )
        trace_question = question or state.current_question or state.answered_question
        tool_records = []
        for call in state.tool_calls or []:
            output_summary = _json_safe(call.get('output_summary') or {})
            retrieval_trace = _json_safe(output_summary.get('retrieval_trace') or {})
            if call.get('ok'):
                call_status = InterviewAgentToolCall.Status.SUCCESS
            elif call.get('error') in (
                'no_approved_rag_context',
                'no_rag_context',
                'no_relevant_context_after_filters',
                'tool_permission_denied',
            ):
                call_status = InterviewAgentToolCall.Status.DEGRADED
            else:
                call_status = InterviewAgentToolCall.Status.FAILED
            tool_records.append(InterviewAgentToolCall(
                session=state.session,
                question=trace_question,
                trace=trace,
                event=state.event,
                node_name='retrieve_knowledge' if call.get('name') == 'knowledge.hybrid_search' else '',
                tool_name=call.get('name') or '',
                subagent_name=call.get('subagent_name') or '',
                permission_scope=call.get('permission_scope') or '',
                status=call_status,
                input_summary=_json_safe(call.get('input_summary') or {}),
                output_summary=output_summary,
                retrieval_trace=retrieval_trace,
                error_message=call.get('error') or '',
                fallback_reason=call.get('fallback_reason') or call.get('error') or '',
                latency_ms=call.get('latency_ms'),
            ))
        if tool_records:
            InterviewAgentToolCall.objects.bulk_create(tool_records)

        memory_records = [
            InterviewAgentMemoryEvent(
                session=state.session,
                question=trace_question,
                trace=trace,
                event_type=event.get('event_type') or InterviewAgentMemoryEvent.EventType.OBSERVATION,
                memory_key=event.get('memory_key') or '',
                dedup_key=event.get('dedup_key') or None,
                value_summary=_json_safe(event.get('value_summary') or {}),
                importance=event.get('importance') or 1,
                source_node=event.get('source_node') or '',
                expires_at=event.get('expires_at'),
            )
            for event in (state.memory_events or [])
        ]
        if memory_records:
            InterviewAgentMemoryEvent.objects.bulk_create(memory_records, ignore_conflicts=True)

    def generate_next_question_stream(self, **kwargs):
        yield from generate_next_question_stream(**kwargs)

    def generate_report(self, **kwargs) -> dict:
        return generate_final_report(**kwargs)


class LangGraphInterviewAgentEngine(DefaultInterviewAgentEngine):
    """LangGraph-backed engine with the same state and persistence contract."""

    def __init__(self):
        self._compiled_submit_graph = None
        self._compiled_regenerate_graph = None
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            logger.warning('LangGraph is not available; falling back to sequential agent runner: %s', exc)
            return

        def wrap(node_func):
            def _node(payload: dict):
                return {'state': node_func(payload['state'])}
            return _node

        def compile_graph(nodes):
            graph = StateGraph(dict)
            for name, func in nodes:
                graph.add_node(name, wrap(func))
            graph.set_entry_point(nodes[0][0])
            for (name, _), (next_name, _) in zip(nodes, nodes[1:]):
                graph.add_edge(name, next_name)
            graph.add_edge(nodes[-1][0], END)
            return graph.compile()

        def skip_node(node_name: str, reason: str):
            def _skip(state):
                self._mark_node(state, node_name, {'skipped': True, 'reason': reason})
                return state
            return _skip

        self._compiled_submit_graph = compile_graph([
            ('load_session_state', self._node_load_session_state),
            ('normalize_multimodal_input', self._node_normalize_multimodal_input),
            ('summarize_environment_context', self._node_summarize_environment_context),
            ('evaluate_answer_rule', self._node_evaluate_answer_rule),
            ('evaluate_answer_ai', self._node_evaluate_answer_ai),
            ('update_coverage', self._node_update_coverage),
            ('update_memory', self._node_update_memory),
            ('load_long_term_memory', self._node_load_long_term_memory),
            ('retrieve_knowledge', self._node_retrieve_knowledge),
            ('plan_next_question', self._node_plan_next_question),
        ])
        self._compiled_regenerate_graph = compile_graph([
            ('load_session_state', self._node_load_session_state),
            ('normalize_multimodal_input', self._node_normalize_multimodal_input),
            ('summarize_environment_context', self._node_summarize_environment_context),
            ('evaluate_answer_rule', skip_node('evaluate_answer_rule', 'already_evaluated')),
            ('evaluate_answer_ai', skip_node('evaluate_answer_ai', 'already_evaluated')),
            ('update_coverage', skip_node('update_coverage', 'already_evaluated')),
            ('update_memory', skip_node('update_memory', 'already_evaluated')),
            ('load_long_term_memory', self._node_load_long_term_memory),
            ('retrieve_knowledge', self._node_retrieve_knowledge),
            ('plan_next_question', self._node_plan_next_question),
        ])

    def prepare_submit_answer_turn(self, **kwargs) -> InterviewAgentState:
        if not self._compiled_submit_graph:
            return super().prepare_submit_answer_turn(**kwargs)
        state = InterviewAgentState(
            session=kwargs['session'],
            user=kwargs['user'],
            current_question=kwargs['current_question'],
            answer_text=kwargs['answer_text'],
            answered_count=kwargs['answered_count'],
            history=kwargs['history'],
            resume_text=kwargs.get('resume_text') or '',
            jd_text=kwargs.get('jd_text') or '',
            media_context=kwargs.get('media_context') or {},
            event='submit_answer_stream',
        )
        result = self._compiled_submit_graph.invoke({'state': state})
        state = result.get('state', state)
        if state.interview_finished:
            state.fallback_reason = 'final_question_no_generation'
            self.persist_trace(state, extra_outputs={'persist_question': {'skipped': True, 'reason': 'interview_finished'}})
        return state

    def prepare_regenerate_question_turn(self, **kwargs) -> InterviewAgentState:
        if not self._compiled_regenerate_graph:
            return super().prepare_regenerate_question_turn(**kwargs)
        answered_question = kwargs['answered_question']
        state = InterviewAgentState(
            session=kwargs['session'],
            user=kwargs['user'],
            answered_question=answered_question,
            current_question=answered_question,
            answer_text=answered_question.answer_text,
            answered_count=kwargs['answered_count'],
            next_sequence=kwargs['answered_count'] + 1,
            history=kwargs['history'],
            resume_text=kwargs.get('resume_text') or '',
            jd_text=kwargs.get('jd_text') or '',
            answer_evaluation=answered_question.ai_feedback if isinstance(answered_question.ai_feedback, dict) else {},
            event='regenerate_next_question',
        )
        result = self._compiled_regenerate_graph.invoke({'state': state})
        return result.get('state', state)


class CompositeInterviewAgentEngine(LangGraphInterviewAgentEngine):
    """Single external interviewer backed by internal logical subagents."""

    SUBAGENT_BY_NODE = {
        'load_session_state': 'ConversationAgent',
        'normalize_multimodal_input': 'ConversationAgent',
        'summarize_environment_context': 'ConversationAgent',
        'evaluate_answer_rule': 'EvaluationAgent',
        'evaluate_answer_ai': 'EvaluationAgent',
        'update_coverage': 'EvaluationAgent',
        'update_memory': 'ConversationAgent',
        'load_long_term_memory': 'MemoryAgent',
        'compress_context': 'MemoryAgent',
        'retrieve_knowledge': 'RetrievalAgent',
        'plan_next_question': 'QuestionPlannerAgent',
        'generate_question': 'QuestionGeneratorAgent',
        'validate_question': 'SafetyAgent',
        'persist_question': 'ConversationAgent',
    }
    LOOP_PHASE_BY_NODE = {
        'load_session_state': 'observe',
        'normalize_multimodal_input': 'observe',
        'summarize_environment_context': 'observe',
        'evaluate_answer_rule': 'act',
        'evaluate_answer_ai': 'act',
        'update_coverage': 'reflect',
        'update_memory': 'reflect',
        'load_long_term_memory': 'observe',
        'compress_context': 'plan',
        'retrieve_knowledge': 'tool_use',
        'plan_next_question': 'plan',
        'generate_question': 'respond',
        'validate_question': 'validate',
        'persist_question': 'reflect',
    }

    def __init__(self):
        self.tool_registry = build_default_tool_registry()
        self.hooks = AgentHookManager()
        self.slash_commands = build_default_slash_commands()
        self.context_budget_manager = ContextBudgetManager()
        super().__init__()

    def _mark_node(self, state: InterviewAgentState, name: str, output: dict | None = None) -> None:
        subagent_name = self.SUBAGENT_BY_NODE.get(name, 'ConversationAgent')
        phase = self.LOOP_PHASE_BY_NODE.get(name, 'act')
        state.subagent_name = subagent_name
        payload = dict(output or {})
        payload.setdefault('_subagent', subagent_name)
        payload.setdefault('_loop_phase', phase)
        payload.setdefault('_loop_iteration', state.loop_iteration or 1)
        state.node_order.append(name)
        state.node_outputs[name] = payload

    def _node_load_session_state(self, state: InterviewAgentState) -> InterviewAgentState:
        snapshot = state.session.agent_config_snapshot or {}
        state.prompt_version = str(
            (snapshot.get('platform') or {}).get('version')
            or normalize_prompt_version()
        )
        state.loop_iteration = state.loop_iteration or 1
        state.context_budget = {
            'token_budget': self.context_budget_manager.token_budget,
            'strategy': 'required_context_plus_relevant_memory_and_rag',
        }
        return super()._node_load_session_state(state)

    def _node_load_long_term_memory(self, state: InterviewAgentState) -> InterviewAgentState:
        return super()._node_load_long_term_memory(state)

    def _node_compress_context(self, state: InterviewAgentState) -> InterviewAgentState:
        canonical_context = assemble_generation_context(
            session=state.session,
            history=state.history,
            rag_context=state.rag_context,
            memory_events=state.retrieved_memory_events,
            media_context=state.media_context,
            task_context=state.question_plan or {},
            current_question=state.current_question.question_text if state.current_question else '',
            candidate_answer=state.answer_text,
            resume_text=state.resume_text,
            jd_text=state.jd_text,
        )
        state.generation_context = canonical_context
        state.compressed_context_summary = {
            **canonical_context,
            # Legacy diagnostics only. Generation reads state.generation_context,
            # so this view cannot become a second prompt context channel.
            'rag_evidence': [
                {
                    **dict(item),
                    'content': str(item.get('content') or '')[:600],
                    'content_preview_hash': hashlib.sha256(
                        str(item.get('content') or '').encode('utf-8')
                    ).hexdigest()[:16],
                }
                for item in (state.rag_context or [])
                if isinstance(item, dict)
            ],
        }
        metadata = canonical_context.get('metadata') or {}
        state.context_budget = {
            'token_budget': metadata.get('token_budget'),
            'estimated_tokens': metadata.get('estimated_tokens'),
            'compression': 'structured_summary',
            'prompt_version': state.prompt_version or normalize_prompt_version(),
        }
        memory = state.session.memory_summary or {}
        memory['context_window'] = {
            'estimated_tokens': state.context_budget.get('estimated_tokens'),
            'token_budget': state.context_budget.get('token_budget'),
            'history_items': len(state.compressed_context_summary.get('conversation_context') or []),
            'memory_recall_items': len(state.compressed_context_summary.get('memory_context') or []),
            'rag_evidence_items': sum(
                1
                for item in state.compressed_context_summary.get('evidence_context') or []
                if item.get('item_type') == 'rag_document'
            ),
        }
        state.session.memory_summary = memory
        state.session.save(update_fields=['memory_summary', 'updated_at'])
        self._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.OBSERVATION,
            memory_key='context_window',
            value_summary=memory['context_window'],
            importance=3,
            source_node='compress_context',
        )
        self._mark_node(state, 'compress_context', state.context_budget)
        return state

    def _build_knowledge_tool_result(self, state: InterviewAgentState) -> AgentToolResult:
        spec = self.tool_registry.get('knowledge.hybrid_search')
        result = super()._build_knowledge_tool_result(state)
        if spec:
            result.subagent_name = spec.subagent_name
            result.permission_scope = spec.permission_scope
            result.fallback_reason = result.error or ''
            result.output_summary = {
                **(result.output_summary or {}),
                'tool_spec': {
                    'name': spec.name,
                    'subagent_name': spec.subagent_name,
                    'permission_scope': spec.permission_scope,
                    'fallback_strategy': spec.fallback_strategy,
                    'timeout_seconds': spec.timeout_seconds,
                },
            }
        return result

    def _node_retrieve_knowledge(self, state: InterviewAgentState) -> InterviewAgentState:
        spec = self.tool_registry.get('knowledge.hybrid_search')
        if spec and not self.tool_registry.is_allowed(spec.name, user=state.user, session=state.session):
            result = AgentToolResult(
                name=spec.name,
                ok=False,
                input_summary={'session_id': str(state.session.id), 'job_position': state.session.job_position},
                output_summary={'source_count': 0, 'reason': 'tool_permission_denied'},
                error='tool_permission_denied',
                subagent_name=spec.subagent_name,
                permission_scope=spec.permission_scope,
                fallback_reason='tool_permission_denied',
            )
            state.tool_calls.append(result.__dict__)
            state.fallback_reason = 'tool_permission_denied'
            self._mark_node(state, 'retrieve_knowledge', result.output_summary)
            return state

        hook_events = self.hooks.run(
            'before_tool_call',
            tool_name='knowledge.hybrid_search',
            state=state,
            subagent_name='RetrievalAgent',
        )
        state = super()._node_retrieve_knowledge(state)
        hook_events.extend(self.hooks.run(
            'after_tool_call',
            tool_name='knowledge.hybrid_search',
            state=state,
            subagent_name='RetrievalAgent',
        ))
        if hook_events:
            state.node_outputs.setdefault('retrieve_knowledge', {})['hooks'] = hook_events
        return state

    def _node_evaluate_answer_ai(self, state: InterviewAgentState) -> InterviewAgentState:
        state = super()._node_evaluate_answer_ai(state)
        hook_events = self.hooks.run(
            'after_answer_evaluate',
            state=state,
            subagent_name='EvaluationAgent',
        )
        if hook_events:
            state.node_outputs.setdefault('evaluate_answer_ai', {})['hooks'] = hook_events
        return state

    def _node_plan_next_question(self, state: InterviewAgentState) -> InterviewAgentState:
        if not state.interview_finished:
            self._node_compress_context(state)
        return super()._node_plan_next_question(state)

    def finalize_generated_question(self, state: InterviewAgentState, full_question_text: str) -> InterviewQuestion:
        hook_events = self.hooks.run(
            'before_question_persist',
            state=state,
            question_text=full_question_text,
            subagent_name='SafetyAgent',
        )
        if hook_events:
            state.node_outputs.setdefault('validate_question', {})['hooks'] = hook_events
        try:
            return super().finalize_generated_question(state, full_question_text)
        except Exception:
            state.node_outputs.setdefault('generate_question', {})['hooks'] = self.hooks.run(
                'on_generation_failed',
                state=state,
                subagent_name='QuestionGeneratorAgent',
            )
            raise

    def parse_slash_command(self, text: str, *, user) -> dict:
        parsed = self.slash_commands.parse(text)
        if not parsed.get('is_command'):
            return parsed
        if not getattr(settings, 'AGENT_ENABLE_SLASH_COMMANDS', True):
            return {**parsed, 'allowed': False, 'reason': 'slash_commands_disabled'}
        spec = self.tool_registry.get('agent.debug')
        allowed = bool(spec and self.tool_registry.is_allowed(spec.name, user=user))
        return {**parsed, 'allowed': allowed, 'reason': '' if allowed else 'permission_denied'}


def get_interview_agent_engine() -> InterviewAgentEngine:
    engine_name = getattr(settings, 'INTERVIEW_AGENT_ENGINE', 'default')
    if engine_name == 'composite_v4':
        from .agent_v4 import CompositeV4InterviewAgentEngine
        return CompositeV4InterviewAgentEngine()
    if engine_name == 'composite_v3':
        from .agent_v3 import CompositeV3InterviewAgentEngine
        return CompositeV3InterviewAgentEngine()
    if engine_name == 'composite_v2':
        from .agent_v2 import CompositeV2InterviewAgentEngine
        return CompositeV2InterviewAgentEngine()
    if engine_name == 'composite':
        return CompositeInterviewAgentEngine()
    if engine_name == 'langgraph':
        return LangGraphInterviewAgentEngine()
    return DefaultInterviewAgentEngine()
