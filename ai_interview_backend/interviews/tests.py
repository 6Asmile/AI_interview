import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .agent import (
    CompositeInterviewAgentEngine,
    DefaultInterviewAgentEngine,
    InterviewAgentState,
    LangGraphInterviewAgentEngine,
    get_interview_agent_engine,
)
from .agent_v2 import CompositeV2InterviewAgentEngine
from .agent_v3 import CompositeV3InterviewAgentEngine
from .agent_runtime import AgentToolExecutor, AgentToolRegistry, AgentToolSpec
from .serializers import InterviewQuestionSerializer
from .evaluation import (
    build_session_plan,
    combine_rule_and_ai_evaluation,
    ensure_default_interview_assets,
    rule_evaluate_answer,
    select_interview_template,
)
from .models import (
    EvaluationDataset,
    InterviewAgentMemoryEvent,
    InterviewAgentNodeRun,
    InterviewAgentRun,
    InterviewAgentToolCall,
    InterviewAgentTrace,
    InterviewMediaArtifact,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewSession,
)
from .ai_services import analyze_resume_against_jd, generate_resume_by_ai, polish_description_by_ai
from .speech_services import synthesize_question_tts, transcribe_bytes
from .views import EvaluationDatasetViewSet, InterviewSessionViewSet, InterviewTemplateViewSet
from users.models import User


class InterviewAgentEngineTests(TestCase):
    @override_settings(INTERVIEW_AGENT_ENGINE='composite_v2')
    def test_composite_v2_engine_switch_returns_recoverable_engine(self):
        engine = get_interview_agent_engine()

        self.assertIsInstance(engine, CompositeV2InterviewAgentEngine)
        self.assertIsNotNone(engine._prepare_graph)
        self.assertIsNotNone(engine._finalize_graph)

    @override_settings(INTERVIEW_AGENT_ENGINE='langgraph')
    def test_langgraph_engine_switch_returns_langgraph_engine(self):
        engine = get_interview_agent_engine()

        self.assertIsInstance(engine, LangGraphInterviewAgentEngine)
        self.assertIsNotNone(engine._compiled_submit_graph)
        self.assertIsNotNone(engine._compiled_regenerate_graph)

    @override_settings(INTERVIEW_AGENT_ENGINE='composite')
    def test_composite_engine_switch_returns_composite_engine(self):
        engine = get_interview_agent_engine()

        self.assertIsInstance(engine, CompositeInterviewAgentEngine)
        self.assertIsNotNone(engine.tool_registry.get('knowledge.hybrid_search'))
        self.assertEqual(engine.tool_registry.get('knowledge.hybrid_search').subagent_name, 'RetrievalAgent')

    def test_initial_memory_uses_ai_profile_for_ai_job(self):
        engine = DefaultInterviewAgentEngine()
        memory, pending_topics = engine.build_initial_memory('AI 应用开发实习生')

        self.assertEqual(memory['prompt_profile'], 'ai_application_intern')
        self.assertIn('RAG/Agent/MCP实践', pending_topics)
        self.assertEqual(memory['rag_context_count'], 0)
        self.assertEqual(memory['asked_question_signatures'], [])
        self.assertEqual(memory['used_knowledge_chunks'], [])

    def test_initial_memory_prefers_jd_custom_profile(self):
        engine = DefaultInterviewAgentEngine()
        memory, pending_topics = engine.build_initial_memory(
            '产品经理',
            jd_text='负责需求分析、PRD、跨团队协作和数据指标复盘。'
        )

        self.assertEqual(memory['prompt_profile'], 'jd_custom')
        self.assertIn('JD核心职责', pending_topics)

    def test_plan_next_question_updates_agent_state(self):
        engine = DefaultInterviewAgentEngine()
        class Session:
            current_stage = 'technical_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = {'unverified_risks': ['RAG召回率'], 'asked_question_signatures': []}

        rag_context = [{'title': 'RAG题库', 'chunk_id': 'chunk-1', 'visibility': 'public', 'ability_tags': ['RAG']}]
        plan = engine.plan_next_question(
            session=Session(),
            history=[{'question': '请介绍一下你的项目', 'answer': '我负责RAG链路设计，包含切分、召回、重排和答案评估，并通过日志指标持续优化。'}],
            rag_context=rag_context,
            last_evaluation={'follow_up_target': '追问RAG召回率优化'},
        )

        self.assertTrue(plan['use_rag'])
        self.assertIn('RAG召回率', plan['target'])
        self.assertIn('chunk-1', Session.memory_summary['used_knowledge_chunks'])
        self.assertTrue(Session.memory_summary['asked_question_signatures'])

    def test_short_answer_plans_clarification_first(self):
        engine = DefaultInterviewAgentEngine()

        class Session:
            current_stage = 'resume_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = {'unverified_risks': ['项目真实性']}

        plan = engine.plan_next_question(
            session=Session(),
            history=[{'question': '请展开讲讲项目。', 'answer': '我做了后端。'}],
            rag_context=[],
            last_evaluation={'follow_up_target': '追问系统设计'},
        )

        self.assertTrue(plan['short_answer_clarification'])
        self.assertIn('回答过短', plan['target'])

    def test_final_question_prioritizes_coverage_gap(self):
        engine = DefaultInterviewAgentEngine()

        class Session:
            current_stage = 'wrap_up'
            difficulty = 'medium'
            question_count = 2
            memory_summary = {'unverified_risks': ['缓存一致性风险']}

        plan = engine.plan_next_question(
            session=Session(),
            history=[{'question': '请介绍项目。', 'answer': '我负责订单系统的缓存设计，包含降级、回源和监控。'}],
            rag_context=[],
            last_evaluation={},
        )

        self.assertTrue(plan['final_gap_priority'])
        self.assertIn('缓存一致性风险', plan['target'])

    def test_environment_context_marks_low_asr_confidence_without_scoring(self):
        engine = DefaultInterviewAgentEngine()
        context = engine._summarize_environment_context(
            [{'timestamp': 1, 'emotions': {'neutral': 0.7, 'happy': 0.2}}],
            {'audio_artifact_id': 'audio-1', 'asr_transcript_meta': {'confidence': 0.4}},
        )

        self.assertEqual(context['dominant_emotion'], 'neutral')
        self.assertTrue(context['has_audio'])
        self.assertTrue(context['low_asr_confidence'])
        self.assertEqual(context['signal_quality'], 'needs_confirmation')
        self.assertIn('low_asr_confidence', context['risk_flags'])
        self.assertFalse(context['use_for_scoring'])
        self.assertEqual(context['scoring_policy'], 'environment_signals_are_for_recovery_and_confirmation_only')

    def test_environment_context_flags_missing_visual_and_asr_confidence(self):
        engine = DefaultInterviewAgentEngine()
        context = engine._summarize_environment_context(
            [],
            {'audio_artifact_id': 'audio-2', 'asr_transcript_meta': {}},
        )

        self.assertEqual(context['frame_count'], 0)
        self.assertEqual(context['visual_signal_quality'], 'unavailable')
        self.assertEqual(context['signal_quality'], 'needs_confirmation')
        self.assertIn('no_visual_frames', context['risk_flags'])
        self.assertIn('asr_confidence_missing', context['risk_flags'])
        self.assertEqual(context['suggested_action'], 'ask_candidate_to_confirm_transcript')
        self.assertFalse(context['use_for_scoring'])

    def test_low_asr_confidence_drives_next_question_confirmation(self):
        engine = DefaultInterviewAgentEngine()

        class Session:
            current_stage = 'technical_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = {
                'environment_context': {
                    'low_asr_confidence': True,
                    'risk_flags': ['low_asr_confidence'],
                    'use_for_scoring': False,
                    'suggested_action': 'confirm_transcript_before_deepening',
                },
                'unverified_risks': ['系统设计证据不足'],
            }

        plan = engine.plan_next_question(
            session=Session(),
            history=[{
                'question': '请介绍你的RAG项目。',
                'answer': '我负责切分、召回、重排和评估，线上召回率有持续监控。',
            }],
            rag_context=[],
            last_evaluation={'follow_up_target': '追问检索质量评估'},
        )

        self.assertTrue(plan['needs_audio_confirmation'])
        self.assertIn('语音转写置信度偏低', plan['target'])
        self.assertFalse(plan['environment_policy']['use_for_scoring'])
        self.assertIn('low_asr_confidence', plan['environment_policy']['risk_flags'])

    def test_tool_observation_is_compacted_into_memory_and_plan(self):
        engine = DefaultInterviewAgentEngine()
        tool_result = {
            'name': 'knowledge.hybrid_search',
            'ok': False,
            'output_summary': {
                'source_count': 0,
                'retrieval_trace': {
                    'vector_count': 0,
                    'keyword_count': 3,
                    'rrf_count': 3,
                    'filtered_count': 3,
                    'rerank_used': False,
                },
            },
            'error': 'no_approved_rag_context',
        }
        memory = engine.remember_tool_observation({}, tool_result)

        self.assertEqual(memory['last_tool_observation']['name'], 'knowledge.hybrid_search')
        self.assertEqual(memory['last_tool_observation']['keyword_count'], 3)
        self.assertEqual(memory['last_tool_observation']['error'], 'no_approved_rag_context')

    def test_tool_observation_keeps_retrieval_explanation_summary(self):
        engine = DefaultInterviewAgentEngine()
        memory = engine.remember_tool_observation({}, {
            'name': 'knowledge.hybrid_search',
            'ok': False,
            'output_summary': {
                'source_count': 0,
                'retrieval_trace': {
                    'vector_count': 2,
                    'keyword_count': 1,
                    'rrf_count': 3,
                    'filtered_count': 3,
                    'rerank_used': False,
                },
                'retrieval_explanation': {
                    'candidate_summary': {'final_count': 0},
                    'filters': {'approval_not_approved': 2, 'tenant_scope_denied': 1},
                    'fallback_reason': 'no_relevant_context_after_filters',
                    'steps': [
                        {'name': 'multi_query', 'status': 'ok'},
                        {'name': 'policy_guard', 'status': 'ok'},
                        {'name': 'rerank', 'status': 'unavailable'},
                    ],
                },
            },
            'error': 'no_relevant_context_after_filters',
        })

        observation = memory['last_tool_observation']
        self.assertEqual(observation['final_count'], 0)
        self.assertEqual(observation['fallback_reason'], 'no_relevant_context_after_filters')
        self.assertEqual(observation['filter_reasons']['approval_not_approved'], 2)
        self.assertEqual(observation['step_statuses']['rerank'], 'unavailable')

        class Session:
            current_stage = 'technical_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = memory

        plan = engine.plan_next_question(
            session=Session(),
            history=[{
                'question': '请介绍你的RAG项目。',
                'answer': '我负责切分、召回、重排和评估，线上召回率有持续监控。',
            }],
            rag_context=[],
            last_evaluation={'follow_up_target': '追问检索质量评估'},
        )

        self.assertEqual(plan['last_tool_observation']['error'], 'no_relevant_context_after_filters')

    def test_long_term_memory_filters_expired_and_orders_by_importance(self):
        user = User.objects.create_user(username='memory-user', email='memory@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.PLAN,
            memory_key='low_priority',
            value_summary={'target': '低优先级'},
            importance=1,
            source_node='plan_next_question',
        )
        high = InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.PLAN,
            memory_key='high_priority',
            value_summary={'target': '优先追问缓存一致性'},
            importance=5,
            source_node='plan_next_question',
        )
        InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.PLAN,
            memory_key='expired',
            value_summary={'target': '已过期'},
            importance=5,
            source_node='plan_next_question',
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        events = DefaultInterviewAgentEngine().load_relevant_memory_events(session=session)

        self.assertEqual(events[0]['id'], high.id)
        self.assertNotIn('expired', [event['memory_key'] for event in events])

    def test_memory_event_retention_policy_sets_expiry_for_transient_signals(self):
        engine = DefaultInterviewAgentEngine()
        state = InterviewAgentState(session=None, user=None)

        engine._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.ENVIRONMENT,
            memory_key='environment_context',
            value_summary={'risk_flags': ['low_asr_confidence']},
            importance=4,
            source_node='summarize_environment_context',
        )
        engine._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.OBSERVATION,
            memory_key='knowledge.hybrid_search',
            value_summary={'source_count': 0, 'error': 'no_approved_rag_context'},
            importance=2,
            source_node='retrieve_knowledge',
        )
        engine._record_memory_event(
            state,
            event_type=InterviewAgentMemoryEvent.EventType.QUESTION,
            memory_key='question:2',
            value_summary={'target': '追问缓存一致性'},
            importance=5,
            source_node='persist_question',
        )

        self.assertIsNotNone(state.memory_events[0]['expires_at'])
        self.assertIsNotNone(state.memory_events[1]['expires_at'])
        self.assertIsNone(state.memory_events[2]['expires_at'])

    def test_long_term_memory_ignores_low_signal_environment_and_empty_tool_observation(self):
        user = User.objects.create_user(username='memory-filter-user', email='memory-filter@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='AI 应用开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.ENVIRONMENT,
            memory_key='environment_context',
            value_summary={'risk_flags': ['no_visual_frames']},
            importance=2,
            source_node='summarize_environment_context',
        )
        InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.OBSERVATION,
            memory_key='knowledge.hybrid_search',
            value_summary={'source_count': 0, 'error': 'no_approved_rag_context'},
            importance=5,
            source_node='retrieve_knowledge',
        )
        successful_tool = InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.OBSERVATION,
            memory_key='knowledge.hybrid_search',
            value_summary={'source_count': 2, 'target': '可用RAG上下文'},
            importance=4,
            source_node='retrieve_knowledge',
        )
        high_environment = InterviewAgentMemoryEvent.objects.create(
            session=session,
            event_type=InterviewAgentMemoryEvent.EventType.ENVIRONMENT,
            memory_key='environment_context',
            value_summary={'risk_flags': ['low_asr_confidence']},
            importance=4,
            source_node='summarize_environment_context',
        )

        events = DefaultInterviewAgentEngine().load_relevant_memory_events(session=session, limit=8)
        event_ids = {event['id'] for event in events}

        self.assertIn(successful_tool.id, event_ids)
        self.assertIn(high_environment.id, event_ids)
        self.assertEqual(len(events), 2)

    def test_plan_next_question_uses_retrieved_memory_when_no_stronger_target(self):
        engine = DefaultInterviewAgentEngine()

        class Session:
            current_stage = 'technical_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = {
                'retrieved_memory_events': [{
                    'event_type': 'plan',
                    'memory_key': 'question_plan',
                    'value_summary': {'target': '候选人缓存一致性证据不足'},
                    'importance': 5,
                    'source_node': 'plan_next_question',
                }],
            }

        plan = engine.plan_next_question(
            session=Session(),
            history=[{
                'question': '请介绍项目。',
                'answer': '我负责订单系统设计，包含接口、缓存和监控，整体效果比较稳定。',
            }],
            rag_context=[],
            last_evaluation={},
        )

        self.assertIn('历史记忆', plan['target'])
        self.assertEqual(plan['memory_recall'][0]['memory_key'], 'question_plan')

    def test_plan_next_question_does_not_use_tool_error_as_target(self):
        engine = DefaultInterviewAgentEngine()

        class Session:
            current_stage = 'technical_deep_dive'
            difficulty = 'medium'
            question_count = 5
            memory_summary = {
                'question_strategy': '继续追问候选人的个人贡献和结果验证。',
                'retrieved_memory_events': [{
                    'event_type': 'observation',
                    'memory_key': 'knowledge.hybrid_search',
                    'value_summary': {'error': 'no_approved_rag_context'},
                    'importance': 5,
                    'source_node': 'retrieve_knowledge',
                }],
            }

        plan = engine.plan_next_question(
            session=Session(),
            history=[{
                'question': '请介绍项目。',
                'answer': '我负责订单系统设计，包含接口、缓存和监控，整体效果比较稳定。',
            }],
            rag_context=[],
            last_evaluation={},
        )

        self.assertNotIn('no_approved_rag_context', plan['target'])
        self.assertEqual(plan['target'], '继续追问候选人的个人贡献和结果验证。')

    def test_finalize_generated_question_records_full_trace_node_order(self):
        user = User.objects.create_user(username='trace-node-user', email='trace-node@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={'asked_question_signatures': []},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        answered_question = InterviewQuestion.objects.create(
            session=session,
            question_text='请介绍一个项目。',
            answer_text='我负责订单服务的缓存和降级。',
            sequence=1,
            answered_at=timezone.now(),
        )
        engine = DefaultInterviewAgentEngine()
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=answered_question,
            answered_count=1,
            question_plan={'target': '追问缓存一致性', 'stage': session.current_stage},
            event='submit_answer_stream',
        )
        engine._mark_node(state, 'load_session_state', {'next_sequence': 2})

        next_question = engine.finalize_generated_question(
            state,
            '请结合订单服务缓存项目，说明你如何处理缓存一致性以及如何验证效果？',
        )

        trace = InterviewAgentTrace.objects.get(session=session)
        self.assertEqual(next_question.sequence, 2)
        self.assertIn('generate_question', trace.output_summary['node_order'])
        self.assertIn('validate_question', trace.output_summary['node_order'])
        self.assertIn('persist_question', trace.output_summary['node_order'])
        self.assertEqual(trace.node_outputs['persist_question']['question_id'], next_question.id)

    def test_finalize_generated_question_collapses_multiple_questions(self):
        user = User.objects.create_user(username='single-question-user', email='single-question@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='AI 应用开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={'asked_question_signatures': []},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        answered_question = InterviewQuestion.objects.create(
            session=session,
            question_text='请介绍一个 RAG 项目。',
            answer_text='我负责检索链路。',
            sequence=1,
            answered_at=timezone.now(),
        )
        engine = DefaultInterviewAgentEngine()
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=answered_question,
            answered_count=1,
            question_plan={'target': '追问RAG评估', 'target_gap': 'RAG评估', 'stage': session.current_stage},
            event='submit_answer_stream',
        )

        next_question = engine.finalize_generated_question(
            state,
            '你如何评估召回率？你如何处理 Rerank 失败？',
        )

        self.assertEqual(state.fallback_reason, 'multiple_questions_collapsed')
        self.assertIn('请只围绕RAG评估', next_question.question_text)
        self.assertEqual(next_question.question_text.count('？'), 0)

    @override_settings(AGENT_CONTEXT_TOKEN_BUDGET=800)
    def test_composite_context_compression_preserves_memory_and_rag_evidence(self):
        user = User.objects.create_user(username='composite-context-user', email='composite-context@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='AI 应用开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={'coverage_gaps': ['RAG评估'], 'question_strategy': '追问检索质量'},
            pending_topics=['RAG', 'Agent'],
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        state = InterviewAgentState(
            session=session,
            user=user,
            history=[{
                'question': '请介绍你的 RAG 项目。',
                'answer': '我负责切分、向量召回、关键词召回、RRF融合和Rerank。',
                'evaluation': {'final_score': 82, 'follow_up_target': '追问RRF评估'},
            }],
            rag_context=[{
                'document_id': 'doc-1',
                'chunk_id': 'chunk-1',
                'title': 'RAG题库',
                'visibility': 'public',
                'ability_tags': ['RAG', '检索'],
                'score': 0.8,
                'content': '企业级混合检索需要记录真实证据。',
            }],
            retrieved_memory_events=[{
                'event_type': 'plan',
                'memory_key': 'question_plan',
                'importance': 5,
                'source_node': 'plan_next_question',
                'value_summary': {'target': '继续验证RAG评估'},
            }],
            media_context={'has_audio': True, 'asr_transcript_meta': {'confidence': 0.9}},
        )
        engine = CompositeInterviewAgentEngine()

        engine._node_load_session_state(state)
        engine._node_compress_context(state)

        self.assertEqual(state.context_budget['compression'], 'structured_summary')
        self.assertEqual(state.compressed_context_summary['rag_evidence'][0]['chunk_id'], 'chunk-1')
        self.assertEqual(state.compressed_context_summary['rag_evidence'][0]['content'], '企业级混合检索需要记录真实证据。')
        self.assertLessEqual(len(state.compressed_context_summary['rag_evidence'][0]['content']), 600)
        self.assertIn('content_preview_hash', state.compressed_context_summary['rag_evidence'][0])
        self.assertEqual(session.memory_summary['context_window']['rag_evidence_items'], 1)
        self.assertIn('compress_context', state.node_order)

    def test_composite_persist_trace_records_subagent_prompt_and_tool_scope(self):
        user = User.objects.create_user(username='composite-trace-user', email='composite-trace@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        question = InterviewQuestion.objects.create(
            session=session,
            question_text='请介绍一个项目。',
            answer_text='我负责订单服务缓存。',
            sequence=1,
            answered_at=timezone.now(),
        )
        engine = CompositeInterviewAgentEngine()
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=question,
            answer_evaluation={'final_score': 76, 'evaluation_mode': 'rule_only_degraded'},
            context_budget={'token_budget': 6000, 'estimated_tokens': 300},
            prompt_version='interview-agent-v1',
            compressed_context_summary={'estimated_tokens': 300, 'rag_evidence': []},
            event='submit_answer_stream',
            tool_calls=[{
                'name': 'knowledge.hybrid_search',
                'ok': False,
                'input_summary': {'job_position': '后端开发'},
                'output_summary': {'source_count': 0, 'retrieval_trace': {'keyword_count': 1}},
                'error': 'no_approved_rag_context',
                'subagent_name': 'RetrievalAgent',
                'permission_scope': 'session_owner',
                'fallback_reason': 'no_approved_rag_context',
            }],
        )
        engine._mark_node(state, 'retrieve_knowledge', {'source_count': 0})

        engine.persist_trace(state)

        trace = InterviewAgentTrace.objects.get(session=session)
        tool_call = InterviewAgentToolCall.objects.get(session=session)
        self.assertEqual(trace.subagent_name, 'RetrievalAgent')
        self.assertEqual(trace.prompt_version, 'interview-agent-v1')
        self.assertEqual(trace.context_budget['estimated_tokens'], 300)
        self.assertEqual(tool_call.subagent_name, 'RetrievalAgent')
        self.assertEqual(tool_call.permission_scope, 'session_owner')
        self.assertEqual(tool_call.fallback_reason, 'no_approved_rag_context')

    @patch('interviews.agent.search_knowledge_context')
    def test_composite_retrieval_tool_denies_non_owner_before_search(self, search_mock):
        owner = User.objects.create_user(username='composite-owner', email='composite-owner@example.com', password='pass')
        other = User.objects.create_user(username='composite-other', email='composite-other@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=owner,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        state = InterviewAgentState(session=session, user=other, history=[])
        engine = CompositeInterviewAgentEngine()

        engine._node_retrieve_knowledge(state)

        search_mock.assert_not_called()
        self.assertEqual(state.tool_calls[0]['error'], 'tool_permission_denied')
        self.assertEqual(state.tool_calls[0]['subagent_name'], 'RetrievalAgent')
        self.assertEqual(state.fallback_reason, 'tool_permission_denied')

    def test_composite_slash_commands_are_admin_or_hr_only(self):
        candidate = User.objects.create_user(username='slash-candidate', email='slash-candidate@example.com', password='pass')
        admin = User.objects.create_user(username='slash-admin', email='slash-admin@example.com', password='pass', is_staff=True)
        engine = CompositeInterviewAgentEngine()

        denied = engine.parse_slash_command('/trace', user=candidate)
        allowed = engine.parse_slash_command('/trace', user=admin)

        self.assertTrue(denied['is_command'])
        self.assertFalse(denied['allowed'])
        self.assertTrue(allowed['allowed'])
        self.assertEqual(allowed['command'], '/trace')

    def test_persist_trace_materializes_tool_calls_and_memory_events(self):
        user = User.objects.create_user(username='tool-memory-user', email='tool-memory@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        question = InterviewQuestion.objects.create(
            session=session,
            question_text='请介绍一个项目。',
            answer_text='我负责订单服务的缓存和降级。',
            sequence=1,
            answered_at=timezone.now(),
        )
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=question,
            answer_evaluation={'final_score': 78, 'evaluation_mode': 'rule_only_degraded'},
            event='submit_answer_stream',
            tool_calls=[{
                'name': 'knowledge.hybrid_search',
                'ok': False,
                'input_summary': {'job_position': '后端开发'},
                'output_summary': {
                    'source_count': 0,
                    'retrieval_trace': {'keyword_count': 2, 'filtered_count': 2},
                },
                'error': 'no_approved_rag_context',
            }],
            memory_events=[{
                'event_type': InterviewAgentMemoryEvent.EventType.OBSERVATION,
                'memory_key': 'knowledge.hybrid_search',
                'value_summary': {'keyword_count': 2, 'error': 'no_approved_rag_context'},
                'importance': 2,
                'source_node': 'retrieve_knowledge',
            }],
        )
        engine = DefaultInterviewAgentEngine()
        engine._mark_node(state, 'retrieve_knowledge', {'source_count': 0})

        engine.persist_trace(state)

        tool_call = InterviewAgentToolCall.objects.get(session=session)
        memory_event = InterviewAgentMemoryEvent.objects.get(session=session)
        self.assertEqual(tool_call.status, InterviewAgentToolCall.Status.DEGRADED)
        self.assertEqual(tool_call.tool_name, 'knowledge.hybrid_search')
        self.assertEqual(tool_call.retrieval_trace['keyword_count'], 2)
        self.assertEqual(memory_event.memory_key, 'knowledge.hybrid_search')
        self.assertEqual(memory_event.trace_id, tool_call.trace_id)

    @patch('interviews.agent.search_knowledge_context')
    def test_retrieve_knowledge_tool_call_persists_retrieval_explanation(self, search_mock):
        user = User.objects.create_user(username='tool-contract-user', email='tool-contract@example.com', password='pass')
        session = InterviewSession.objects.create(
            user=user,
            job_position='AI 应用开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
            memory_summary={'used_knowledge_chunks': []},
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
        )
        question = InterviewQuestion.objects.create(
            session=session,
            question_text='请介绍你的 RAG 项目。',
            answer_text='我负责切分、召回、RRF融合和Rerank。',
            sequence=1,
            answered_at=timezone.now(),
        )
        search_mock.return_value = {
            'contexts': [{
                'document_id': 'doc-1',
                'chunk_id': 'chunk-1',
                'title': 'RAGFlow 风格题库',
                'visibility': 'public',
                'ability_tags': ['RAG'],
                'score': 0.12,
                'content': '追问混合检索链路。',
            }],
            'retrieval_trace': {'vector_count': 1, 'keyword_count': 1, 'rrf_count': 1, 'filtered_count': 0},
            'retrieval_explanation': {
                'candidate_summary': {'final_count': 1, 'rrf_count': 1},
                'filters': {},
                'fallback_reason': '',
                'steps': [{'name': 'multi_query', 'status': 'ok'}],
            },
        }
        state = InterviewAgentState(
            session=session,
            user=user,
            current_question=question,
            answered_count=1,
            history=[{'question': question.question_text, 'answer': question.answer_text}],
            answer_evaluation={'follow_up_target': '追问混合检索'},
            event='submit_answer_stream',
        )
        engine = DefaultInterviewAgentEngine()

        engine._node_retrieve_knowledge(state)
        engine.persist_trace(state, question=question)

        tool_call = InterviewAgentToolCall.objects.get(session=session)
        self.assertEqual(tool_call.status, InterviewAgentToolCall.Status.SUCCESS)
        self.assertEqual(tool_call.output_summary['retrieval_explanation']['candidate_summary']['final_count'], 1)
        self.assertEqual(tool_call.output_summary['sources'][0]['chunk_id'], 'chunk-1')
        self.assertEqual(session.memory_summary['last_tool_observation']['final_count'], 1)


class InterviewAgentTraceViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='owner', email='owner@example.com', password='pass')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='pass')
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='pass', is_staff=True)
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        question = InterviewQuestion.objects.create(
            session=self.session,
            question_text='请介绍项目。',
            sequence=1,
        )
        InterviewAgentTrace.objects.create(
            session=self.session,
            question=question,
            event='submit_answer_stream',
            stage='technical_deep_dive',
            generated_question='请继续说明缓存一致性方案。',
            fallback_reason='no_rag_context',
        )
        self.trace = self.session.agent_traces.first()
        InterviewAgentToolCall.objects.create(
            session=self.session,
            question=question,
            trace=self.trace,
            event='submit_answer_stream',
            node_name='retrieve_knowledge',
            tool_name='knowledge.hybrid_search',
            status=InterviewAgentToolCall.Status.DEGRADED,
            input_summary={'job_position': '后端开发'},
            output_summary={'source_count': 0},
            retrieval_trace={'keyword_count': 1},
            error_message='no_approved_rag_context',
        )
        InterviewAgentMemoryEvent.objects.create(
            session=self.session,
            question=question,
            trace=self.trace,
            event_type=InterviewAgentMemoryEvent.EventType.PLAN,
            memory_key='question_plan',
            value_summary={'target': '追问缓存一致性'},
            importance=4,
            source_node='plan_next_question',
        )

    def test_owner_can_read_agent_traces(self):
        view = InterviewSessionViewSet.as_view({'get': 'agent_traces'})
        request = self.factory.get(f'/interviews/{self.session.id}/agent-traces/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['fallback_reason'], 'no_rag_context')

    def test_other_user_cannot_read_agent_traces(self):
        view = InterviewSessionViewSet.as_view({'get': 'agent_traces'})
        request = self.factory.get(f'/interviews/{self.session.id}/agent-traces/')
        force_authenticate(request, user=self.other)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 404)

    def test_admin_can_read_agent_traces(self):
        view = InterviewSessionViewSet.as_view({'get': 'agent_traces'})
        request = self.factory.get(f'/interviews/{self.session.id}/agent-traces/')
        force_authenticate(request, user=self.admin)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_owner_can_read_agent_tool_calls(self):
        view = InterviewSessionViewSet.as_view({'get': 'agent_tool_calls'})
        request = self.factory.get(f'/interviews/{self.session.id}/agent-tool-calls/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['tool_name'], 'knowledge.hybrid_search')
        self.assertEqual(response.data[0]['status'], InterviewAgentToolCall.Status.DEGRADED)

    def test_owner_can_read_agent_memory_events(self):
        view = InterviewSessionViewSet.as_view({'get': 'agent_memory_events'})
        request = self.factory.get(f'/interviews/{self.session.id}/agent-memory-events/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['memory_key'], 'question_plan')
        self.assertEqual(response.data[0]['importance'], 4)


class EnterpriseInterviewSystemTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.candidate = User.objects.create_user(username='candidate', email='c@example.com', password='pass')
        self.hr = User.objects.create_user(username='hr', email='hr@example.com', password='pass', role=User.Role.HR)

    def test_default_template_snapshot_has_dimensions_and_stage_plan(self):
        ensure_default_interview_assets()
        template = select_interview_template('AI 应用开发实习生')
        plan, snapshot = build_session_plan(template, 5, 'AI 应用开发实习生', '')

        self.assertIn('dimensions', snapshot)
        self.assertGreaterEqual(len(snapshot['dimensions']), 5)
        self.assertEqual(plan['question_count'], 5)
        self.assertTrue(plan['coverage_gaps'])

    def test_rule_evaluation_scores_specific_answer_higher_than_short_answer(self):
        short_result = rule_evaluate_answer('请介绍你的RAG项目。', '我做过。')
        strong_result = rule_evaluate_answer(
            '请介绍你的RAG项目。',
            '我负责企业知识库RAG链路设计，先根据业务文档特点确定chunk大小和overlap，再对比embedding模型和rerank效果。上线后命中率提升18%，客服平均响应时间降低到2秒以内。',
        )

        self.assertLess(short_result['rule_score'], strong_result['rule_score'])
        self.assertIn('answer_too_short', short_result['risk_flags'])
        self.assertTrue(strong_result['evidence_items'])

    def test_ai_missing_uses_rule_only_degraded_mode(self):
        rule_result = rule_evaluate_answer('请说明缓存一致性方案。', '我负责缓存设计，增加版本号和回源校验，线上错误率降低30%。')
        result = combine_rule_and_ai_evaluation(rule_result, {})

        self.assertEqual(result['evaluation_mode'], 'rule_only_degraded')
        self.assertEqual(result['final_score'], rule_result['rule_score'])

    def test_candidate_cannot_create_evaluation_dataset(self):
        view = EvaluationDatasetViewSet.as_view({'post': 'create'})
        request = self.factory.post('/evaluation-datasets/', {'name': '真实匿名化样例集'}, format='json')
        force_authenticate(request, user=self.candidate)

        response = view(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(EvaluationDataset.objects.count(), 0)

    def test_hr_can_list_default_templates(self):
        ensure_default_interview_assets()
        view = InterviewTemplateViewSet.as_view({'get': 'list'})
        request = self.factory.get('/interview-templates/')
        force_authenticate(request, user=self.hr)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        results = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(results), 3)


class ResumeGenerationSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='resume-ai-user', email='resume-ai@example.com', password='pass')

    @patch('interviews.ai_services._get_user_ai_config')
    @patch('interviews.ai_services._call_openai_api')
    def test_generate_resume_without_evidence_returns_scaffold_without_calling_ai(self, call_ai, config):
        config.return_value = ('key', object())

        result = generate_resume_by_ai(
            name='张三',
            position='AI 应用开发',
            experience_years='1年',
            keywords='Python, RAG, LangGraph',
            user=self.user,
        )

        call_ai.assert_not_called()
        self.assertEqual(result['meta']['generation_mode'], 'evidence_required_scaffold')
        work_module = next(item for item in result['main'] if item['moduleType'] == 'WorkExp')
        project_module = next(item for item in result['main'] if item['moduleType'] == 'Project')
        education_module = next(item for item in result['main'] if item['moduleType'] == 'Education')
        self.assertEqual(work_module['props']['experiences'], [])
        self.assertEqual(project_module['props']['projects'], [])
        self.assertEqual(education_module['props']['educations'], [])
        self.assertIn('不会代为编造', project_module['props']['placeholder'])

    @patch('interviews.ai_services._get_user_ai_config')
    @patch('interviews.ai_services._call_openai_api')
    def test_generate_resume_sanitizes_fabricated_sections_when_evidence_is_weak(self, call_ai, config):
        config.return_value = ('key', object())
        call_ai.return_value = {
            'sidebar': [{
                'id': 'skills',
                'componentName': 'SkillsModule',
                'moduleType': 'Skills',
                'title': '专业技能',
                'props': {'skills': [{'id': 's1', 'name': 'RAG', 'proficiency': '熟练'}]},
            }],
            'main': [{
                'id': 'project',
                'componentName': 'ProjectModule',
                'moduleType': 'Project',
                'title': '项目经历',
                'props': {
                    'projects': [{
                        'id': 'p1',
                        'name': '虚构电商推荐系统',
                        'role': '负责人',
                        'description': '提升转化率30%',
                    }]
                },
            }],
        }

        # 直接测试清洗路径：即便模型返回伪造内容，弱证据输入也不允许落库。
        from .ai_services import _sanitize_resume_json
        result = _sanitize_resume_json(
            call_ai.return_value,
            name='李四',
            position='后端开发',
            experience_years='0年',
            keywords='Java, Redis',
        )

        project_module = next(item for item in result['main'] if item['moduleType'] == 'Project')
        self.assertEqual(result['meta']['generation_mode'], 'evidence_required_scaffold')
        self.assertEqual(project_module['props']['projects'], [])
        self.assertIn('不会代为编造', project_module['props']['placeholder'])

    @patch('interviews.ai_services._get_user_ai_config')
    @patch('interviews.ai_services._call_openai_api')
    def test_generate_resume_with_real_evidence_calls_ai_with_no_fabrication_policy(self, call_ai, config):
        config.return_value = ('key', type('Model', (), {'base_url': 'http://model', 'model_slug': 'chat'})())
        call_ai.return_value = {
            'sidebar': [],
            'main': [],
            'meta': {'generation_mode': 'evidence_guarded_ai'},
        }

        result = generate_resume_by_ai(
            name='王五',
            position='AI 应用开发',
            experience_years='2年',
            keywords='2025年在真实客服RAG项目中负责文档切分、向量召回和Rerank，上线后人工检索时间降低20%。',
            user=self.user,
        )

        self.assertEqual(result['meta']['generation_mode'], 'evidence_guarded_ai')
        messages = call_ai.call_args.args[2]
        prompt_text = '\n'.join(item['content'] for item in messages)
        self.assertIn('禁止编造公司、学校、项目', prompt_text)
        self.assertNotIn('合理的虚构和扩展', prompt_text)

    @patch('interviews.ai_services._get_user_ai_config')
    @patch('interviews.ai_services._call_openai_api')
    def test_polish_description_rejects_new_numeric_claims(self, call_ai, config):
        config.return_value = ('key', type('Model', (), {'base_url': 'http://model', 'model_slug': 'chat'})())
        original_html = '<ul><li>负责 RAG 检索模块开发。</li></ul>'
        call_ai.return_value = {
            'polished_html': '<ul><li>负责 RAG 检索模块开发，使召回率提升 30%。</li></ul>'
        }

        result = polish_description_by_ai(original_html, self.user, job_position='AI 应用开发')

        self.assertEqual(result, original_html)
        prompt_text = '\n'.join(item['content'] for item in call_ai.call_args.args[2])
        self.assertIn('禁止新增用户原文没有提供', prompt_text)

    @patch('interviews.ai_services._get_user_ai_config')
    @patch('interviews.ai_services._call_openai_api')
    def test_analyze_resume_sanitizes_suggestions_with_unsupported_numbers(self, call_ai, config):
        config.return_value = ('key', type('Model', (), {'base_url': 'http://model', 'model_slug': 'chat'})())
        call_ai.return_value = {
            'overall_score': 72,
            'ability_scores': [{'name': '经验的量化成果', 'score': '2'}],
            'keyword_analysis': {
                'jd_keywords': ['RAG'],
                'matched_keywords': ['RAG'],
                'missing_keywords': [],
            },
            'strengths_analysis': ['有 RAG 项目描述'],
            'weaknesses_analysis': ['缺少结果证据'],
            'suggestions': [{
                'module': '项目经历',
                'suggestion': '将项目描述改为：通过 Rerank 将准确率从 70% 提升到 92%。',
            }],
        }

        result = analyze_resume_against_jd(
            resume_text='负责 RAG 检索模块开发。',
            jd_text='要求熟悉 RAG 和 Rerank。',
            user=self.user,
        )

        suggestion = result['suggestions'][0]
        self.assertTrue(suggestion['unsupported_claim'])
        self.assertIn('系统不会代为编造具体数字', suggestion['suggestion'])
        self.assertEqual(result['evidence_policy'], 'analysis_must_reference_resume_or_jd; suggestions_must_not_invent_metrics')
        self.assertEqual(result['ability_scores'][0]['score'], 2.0)


class InterviewSpeechServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='voice-user', email='voice@example.com', password='pass')
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            question_text='请介绍一个你主导的项目。',
            sequence=1,
        )

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': '', 'ASR_API_KEY': ''})
    def test_asr_missing_config_does_not_fake_transcript(self):
        result = transcribe_bytes(
            session=self.session,
            question=self.question,
            user=self.user,
            audio_bytes=b'not-real-audio',
            filename='answer.webm',
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, 'asr_model_or_api_key_missing')
        artifact = InterviewMediaArtifact.objects.get(id=result.artifact.id)
        self.assertEqual(artifact.status, InterviewMediaArtifact.Status.FAILED)
        self.assertEqual(artifact.transcript_text, '')

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': '', 'TTS_API_KEY': ''})
    def test_tts_missing_config_returns_failed_artifact(self):
        result = synthesize_question_tts(
            session=self.session,
            question=self.question,
            user=self.user,
            text=self.question.question_text,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, 'tts_model_or_api_key_missing')
        artifact = InterviewMediaArtifact.objects.get(id=result.artifact.id)
        self.assertEqual(artifact.status, InterviewMediaArtifact.Status.FAILED)
        self.assertFalse(bool(artifact.source_file))

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': '', 'TTS_API_KEY': ''})
    def test_tts_cache_requires_matching_text_hash(self):
        cached = InterviewMediaArtifact.objects.create(
            session=self.session,
            question=self.question,
            user=self.user,
            artifact_type=InterviewMediaArtifact.ArtifactType.QUESTION_TTS,
            status=InterviewMediaArtifact.Status.COMPLETED,
            mime_type='audio/mpeg',
            metadata={
                'text_hash': hashlib.sha256('旧问题文本'.encode('utf-8')).hexdigest(),
                'synthesized_at': timezone.now().isoformat(),
            },
        )
        cached.source_file.save('cached-question.mp3', ContentFile(b'cached-audio'), save=True)

        result = synthesize_question_tts(
            session=self.session,
            question=self.question,
            user=self.user,
            text='新的问题文本',
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, 'tts_model_or_api_key_missing')
        self.assertNotEqual(result.artifact.id, cached.id)


class InterviewMediaArtifactPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='media-owner', email='media-owner@example.com', password='pass')
        self.other = User.objects.create_user(username='media-other', email='media-other@example.com', password='pass')
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            question_text='请介绍一个你主导的项目。',
            sequence=1,
        )
        self.other_artifact = InterviewMediaArtifact.objects.create(
            session=self.session,
            question=self.question,
            user=self.other,
            artifact_type=InterviewMediaArtifact.ArtifactType.ANSWER_AUDIO,
            status=InterviewMediaArtifact.Status.COMPLETED,
            transcript_text='其他用户的转写文本',
        )

    def test_submit_answer_rejects_audio_artifact_from_other_user(self):
        view = InterviewSessionViewSet.as_view({'post': 'submit_answer_stream'})
        request = self.factory.post(
            f'/interviews/{self.session.id}/submit-answer-stream/',
            {
                'question_id': self.question.id,
                'answer_text': '我负责订单系统缓存设计，包含回源、降级和监控。',
                'audio_artifact_id': str(self.other_artifact.id),
            },
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], '语音记录不存在或无权使用')
        self.question.refresh_from_db()
        self.assertIsNone(self.question.answered_at)


class InterviewQuestionGenerationJobTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='generation-owner', email='generation@example.com', password='pass')
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            question_count=3,
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            question_text='请介绍一个你主导的项目。',
            answer_text='我负责订单系统缓存设计，包含回源、降级和监控。',
            ai_feedback={'feedback': '回答有效', 'final_score': 75},
            sequence=1,
            answered_at=timezone.now(),
        )

    def test_regenerate_rejects_recent_running_generation_job(self):
        InterviewQuestionGenerationJob.objects.create(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            status=InterviewQuestionGenerationJob.Status.RUNNING,
            request_hash='hash-1',
            engine_name='langgraph',
            started_at=timezone.now(),
        )
        view = InterviewSessionViewSet.as_view({'post': 'regenerate_next_question'})
        request = self.factory.post(
            f'/interviews/{self.session.id}/regenerate-next-question/',
            {'question_id': self.question.id},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['generation_job']['status'], InterviewQuestionGenerationJob.Status.RUNNING)
        self.assertFalse(response.data['generation_job']['can_retry'])
        self.assertFalse(response.data['generation_job']['is_stale'])
        self.assertGreaterEqual(response.data['generation_job']['retry_after_seconds'], 0)
        self.assertEqual(self.session.questions.count(), 1)

    @override_settings(INTERVIEW_GENERATION_JOB_STALE_SECONDS=30)
    def test_stale_running_generation_job_is_reset_for_retry(self):
        stale_job = InterviewQuestionGenerationJob.objects.create(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            status=InterviewQuestionGenerationJob.Status.RUNNING,
            request_hash='old-hash',
            engine_name='default',
            partial_text='旧的半截问题',
            started_at=timezone.now() - timedelta(minutes=5),
        )
        InterviewQuestionGenerationJob.objects.filter(id=stale_job.id).update(
            updated_at=timezone.now() - timedelta(minutes=5)
        )
        viewset = InterviewSessionViewSet()

        job, can_generate = viewset._get_or_start_generation_job(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            request_hash='new-hash',
            engine_name='langgraph',
        )

        self.assertEqual(job.id, stale_job.id)
        self.assertTrue(can_generate)
        self.assertEqual(job.status, InterviewQuestionGenerationJob.Status.RUNNING)
        self.assertEqual(job.request_hash, 'new-hash')
        self.assertEqual(job.engine_name, 'langgraph')
        self.assertEqual(job.partial_text, '')
        self.assertEqual(job.error_message, '')
        self.assertIsNone(job.completed_at)

    def test_failed_generation_job_is_reset_for_retry(self):
        failed_job = InterviewQuestionGenerationJob.objects.create(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            status=InterviewQuestionGenerationJob.Status.FAILED,
            request_hash='old-hash',
            engine_name='default',
            partial_text='旧的半截问题',
            final_text='不完整问题',
            error_message='stream_disconnected',
            started_at=timezone.now() - timedelta(minutes=5),
            completed_at=timezone.now() - timedelta(minutes=4),
        )
        viewset = InterviewSessionViewSet()

        job, can_generate = viewset._get_or_start_generation_job(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            request_hash='new-hash',
            engine_name='langgraph',
        )

        self.assertEqual(job.id, failed_job.id)
        self.assertTrue(can_generate)
        self.assertEqual(job.status, InterviewQuestionGenerationJob.Status.RUNNING)
        self.assertEqual(job.request_hash, 'new-hash')
        self.assertEqual(job.engine_name, 'langgraph')
        self.assertEqual(job.partial_text, '')
        self.assertEqual(job.final_text, '')
        self.assertEqual(job.error_message, '')
        self.assertIsNone(job.completed_at)

    def test_owner_can_read_question_generation_jobs(self):
        InterviewQuestionGenerationJob.objects.create(
            session=self.session,
            answered_question=self.question,
            sequence=2,
            status=InterviewQuestionGenerationJob.Status.FAILED,
            error_message='stream_disconnected',
        )
        view = InterviewSessionViewSet.as_view({'get': 'question_generation_jobs'})
        request = self.factory.get(f'/interviews/{self.session.id}/question-generation-jobs/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(self.session.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['sequence'], 2)
        self.assertEqual(response.data[0]['status'], InterviewQuestionGenerationJob.Status.FAILED)


@override_settings(
    INTERVIEW_AGENT_ENGINE='composite_v2',
    AGENT_MAX_GENERATION_RETRIES=2,
    AGENT_EVALUATION_CONFIDENCE_THRESHOLD=0.6,
)
class CompositeV2AgentTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username='v2-candidate', email='v2@example.com', password='pass')
        self.admin = User.objects.create_user(username='v2-admin', email='v2-admin@example.com', password='pass', is_staff=True)
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='AI 应用开发',
            difficulty=InterviewSession.Difficulty.MEDIUM,
            question_count=3,
            status=InterviewSession.Status.RUNNING,
            current_stage=InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
            started_at=timezone.now(),
            session_plan={
                'dimensions': [{'key': 'evidence', 'name': '证据质量', 'weight': 1}],
                'coverage_requirements': {'evidence': {'min_coverage': 1}},
                'coverage': {},
                'coverage_gaps': ['evidence'],
            },
            coverage_summary={'coverage': {}, 'coverage_gaps': ['evidence']},
            memory_summary={
                'asked_question_signatures': [],
                'used_knowledge_chunks': [],
                'coverage_gaps': ['evidence'],
            },
            pending_topics=['证据质量'],
        )
        self.answer = (
            '我负责企业知识库RAG检索链路，设计了向量召回、关键词召回、RRF融合和Rerank。'
            '上线前使用真实问答集评估，命中率提升18%，平均响应时间降低到2秒，并持续分析失败样例。'
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            question_text='请说明你如何评估RAG系统的检索质量？',
            answer_text=self.answer,
            sequence=1,
            answered_at=timezone.now(),
            question_plan={
                'stage': InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
                'target_stage': InterviewSession.InterviewStage.TECHNICAL_DEEP_DIVE,
                'target_dimension': 'evidence',
                'target_gap': 'evidence',
            },
            target_dimension='evidence',
            validation_status='validated',
        )

    def _history(self):
        return [{
            'sequence': 1,
            'question': self.question.question_text,
            'answer': self.answer,
            'evaluation': {},
            'rag_context': [],
        }]

    @patch('interviews.agent.search_knowledge_context')
    def test_prepare_graph_degrades_without_ai_and_persists_node_checkpoints(self, search_mock):
        search_mock.return_value = {
            'contexts': [],
            'retrieval_trace': {'keyword_count': 0, 'vector_count': 0},
            'retrieval_explanation': {'fallback_reason': 'no_approved_rag_context'},
        }
        engine = CompositeV2InterviewAgentEngine()

        state = engine.prepare_submit_answer_turn(
            session=self.session,
            current_question=self.question,
            answer_text=self.answer,
            user=self.user,
            answered_count=1,
            history=self._history(),
            resume_text='',
            jd_text='',
            media_context={},
        )

        run = InterviewAgentRun.objects.get(id=state.agent_run_id)
        self.assertEqual(run.status, InterviewAgentRun.Status.WAITING_GENERATION)
        self.assertIn('rule_degrade', state.node_order)
        self.assertEqual(state.answer_evaluation['evaluation_mode'], 'rule_only_degraded')
        self.assertTrue(run.node_runs.filter(node_name='strategy_plan', status=InterviewAgentNodeRun.Status.SUCCEEDED).exists())
        self.question.refresh_from_db()
        self.assertEqual(self.question.ai_feedback['agent_run_id'], str(run.id))
        self.session.refresh_from_db()
        self.assertEqual(self.session.coverage_summary['coverage']['evidence'], 1)

    @patch('interviews.agent.search_knowledge_context')
    def test_context_assembly_injects_bounded_real_rag_evidence(self, search_mock):
        search_mock.return_value = {
            'contexts': [{
                'document_id': 1,
                'chunk_id': 'chunk-v2',
                'title': 'RAG质量评估',
                'visibility': 'public',
                'ability_tags': ['evidence'],
                'score': 0.91,
                'content': '使用真实评估集计算召回率，并分析未命中问题。' * 30,
            }],
            'retrieval_trace': {'keyword_count': 1, 'vector_count': 1, 'rrf_count': 1},
            'retrieval_explanation': {'fallback_reason': ''},
        }
        engine = CompositeV2InterviewAgentEngine()

        state = engine.prepare_submit_answer_turn(
            session=self.session,
            current_question=self.question,
            answer_text=self.answer,
            user=self.user,
            answered_count=1,
            history=self._history(),
            resume_text='',
            jd_text='',
            media_context={},
        )

        evidence = state.generation_context['rag_evidence'][0]
        self.assertEqual(evidence['chunk_id'], 'chunk-v2')
        self.assertTrue(evidence['content'])
        self.assertLessEqual(len(evidence['content']), 600)
        self.assertLessEqual(state.context_budget['estimated_tokens'], state.context_budget['token_budget'])

    @patch('interviews.agent.search_knowledge_context')
    def test_invalid_generation_retries_then_uses_validated_safe_fallback(self, search_mock):
        search_mock.return_value = {
            'contexts': [],
            'retrieval_trace': {},
            'retrieval_explanation': {'fallback_reason': 'no_approved_rag_context'},
        }
        engine = CompositeV2InterviewAgentEngine()
        state = engine.prepare_submit_answer_turn(
            session=self.session,
            current_question=self.question,
            answer_text=self.answer,
            user=self.user,
            answered_count=1,
            history=self._history(),
            resume_text='',
            jd_text='',
            media_context={},
        )

        next_question = engine.finalize_generated_question(state, '你做了什么？结果如何？')

        self.assertEqual(next_question.validation_status, 'validated')
        self.assertEqual(next_question.generation_mode, 'safe_fallback')
        self.assertEqual(next_question.question_text.count('？') + next_question.question_text.count('?'), 1)
        run = InterviewAgentRun.objects.get(id=state.agent_run_id)
        self.assertEqual(run.status, InterviewAgentRun.Status.DEGRADED)
        self.assertEqual(run.node_runs.filter(node_name='repair').count(), 2)
        self.assertTrue(run.node_runs.filter(node_name='safe_fallback').exists())
        self.assertEqual(run.traces.count(), 1)

    @patch('interviews.agent.search_knowledge_context')
    def test_repeating_prepare_is_idempotent_for_coverage(self, search_mock):
        search_mock.return_value = {'contexts': [], 'retrieval_trace': {}, 'retrieval_explanation': {}}
        engine = CompositeV2InterviewAgentEngine()
        kwargs = {
            'session': self.session,
            'current_question': self.question,
            'answer_text': self.answer,
            'user': self.user,
            'answered_count': 1,
            'history': self._history(),
            'resume_text': '',
            'jd_text': '',
            'media_context': {},
        }

        first = engine.prepare_submit_answer_turn(**kwargs)
        second = engine.prepare_submit_answer_turn(**kwargs)

        self.assertEqual(first.agent_run_id, second.agent_run_id)
        self.session.refresh_from_db()
        self.assertEqual(self.session.coverage_summary['coverage']['evidence'], 1)
        self.assertEqual(InterviewAgentRun.objects.count(), 1)

    def test_candidate_gets_run_summary_but_admin_gets_node_details(self):
        run = InterviewAgentRun.objects.create(
            session=self.session,
            trigger_question=self.question,
            event='submit_answer_stream',
            request_hash='a' * 64,
            status=InterviewAgentRun.Status.COMPLETED,
        )
        InterviewAgentNodeRun.objects.create(
            run=run,
            node_name='load_context',
            subagent_name='ConversationAgent',
            status=InterviewAgentNodeRun.Status.SUCCEEDED,
            attempt=1,
        )
        view = InterviewSessionViewSet.as_view({'get': 'agent_run_detail'})

        candidate_request = self.factory.get(f'/interviews/{self.session.id}/agent-runs/{run.id}/')
        force_authenticate(candidate_request, user=self.user)
        candidate_response = view(candidate_request, pk=str(self.session.id), run_id=str(run.id))
        admin_request = self.factory.get(f'/interviews/{self.session.id}/agent-runs/{run.id}/')
        force_authenticate(admin_request, user=self.admin)
        admin_response = view(admin_request, pk=str(self.session.id), run_id=str(run.id))

        self.assertEqual(candidate_response.status_code, 200)
        self.assertEqual(candidate_response.data['node_runs'], [])
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.data['node_runs'][0]['node_name'], 'load_context')

    def test_report_agent_only_uses_supported_evidence(self):
        self.question.ai_feedback = {
            'final_score': 82,
            'confidence': 0.85,
            'evidence_items': [
                {'type': 'metric_result', 'quote': '命中率提升18%', 'supported': True},
                {'type': 'invented', 'quote': '不存在的证据', 'supported': False},
            ],
            'risk_flags': ['insufficient_tradeoff'],
            'rubric_scores': [{'dimension_key': 'evidence', 'score': 82}],
        }
        self.question.save(update_fields=['ai_feedback'])
        engine = CompositeV2InterviewAgentEngine()

        report = engine.generate_report(session=self.session)

        self.assertEqual(report['report_generation_mode'], 'evidence_guarded_composite_v2')
        self.assertIn('命中率提升18%', report['strength_analysis'])
        self.assertNotIn('不存在的证据', report['strength_analysis'])
        self.assertEqual(report['evidence_chain'][0]['evidence_items'][0]['supported'], True)
        run = InterviewAgentRun.objects.get(event='finish_report')
        self.assertEqual(run.status, InterviewAgentRun.Status.COMPLETED)
        self.assertTrue(run.node_runs.filter(subagent_name='ReportAgent').exists())

    @patch('interviews.agent.search_knowledge_context')
    def test_submit_answer_stream_keeps_api_contract_and_exposes_run_id(self, search_mock):
        search_mock.return_value = {'contexts': [], 'retrieval_trace': {}, 'retrieval_explanation': {}}
        session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            difficulty=InterviewSession.Difficulty.MEDIUM,
            question_count=2,
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
            session_plan={
                'dimensions': [{'key': 'evidence', 'name': '证据质量', 'weight': 1}],
                'coverage_requirements': {'evidence': {'min_coverage': 1}},
                'coverage': {},
                'coverage_gaps': ['evidence'],
            },
            coverage_summary={'coverage': {}, 'coverage_gaps': ['evidence']},
            memory_summary={'asked_question_signatures': [], 'used_knowledge_chunks': []},
        )
        question = InterviewQuestion.objects.create(
            session=session,
            sequence=1,
            question_text='请介绍一个你负责的项目？',
            question_plan={'target_dimension': 'evidence', 'stage': 'opening', 'target_stage': 'opening'},
            target_dimension='evidence',
        )
        view = InterviewSessionViewSet.as_view({'post': 'submit_answer_stream'})
        request = self.factory.post(
            f'/interviews/{session.id}/submit-answer-stream/',
            {'question_id': question.id, 'answer_text': self.answer},
            format='json',
        )
        force_authenticate(request, user=self.user)

        response = view(request, pk=str(session.id))
        body = b''.join(response.streaming_content).decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['X-Agent-Run-Id'])
        self.assertIn('X-Agent-Run-Id', response['Access-Control-Expose-Headers'])
        self.assertIn('__FINAL_QUESTION__:', body)
        run = InterviewAgentRun.objects.get(id=response['X-Agent-Run-Id'])
        self.assertIn(run.status, (InterviewAgentRun.Status.COMPLETED, InterviewAgentRun.Status.DEGRADED))
        self.assertTrue(session.questions.filter(sequence=2, validation_status='validated').exists())


@override_settings(INTERVIEW_AGENT_ENGINE='composite_v3')
class CompositeV3AdaptiveAgentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='v3-candidate', email='v3@example.com', password='pass')
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            question_count=5,
            target_duration_minutes=30,
            experience_mode=InterviewSession.ExperienceMode.REALISTIC,
            interview_mode='project_with_fundamentals',
            progress_mode='time_and_coverage',
            status=InterviewSession.Status.RUNNING,
            current_stage=InterviewSession.InterviewStage.PROJECT_DEEP_DIVE,
            started_at=timezone.now(),
            session_plan={
                'dimensions': [{'key': 'technical_depth', 'name': '技术深度', 'weight': 2}],
                'coverage_requirements': {'technical_depth': {'min_coverage': 1, 'weight': 2}},
                'coverage': {},
                'coverage_gaps': ['technical_depth'],
                'termination_policy': {
                    'target_duration_minutes': 30,
                    'min_duration_minutes': 20,
                    'hard_max_duration_minutes': 45,
                    'min_turns': 5,
                    'max_turns': 18,
                },
            },
            coverage_summary={'coverage': {}, 'coverage_gaps': ['technical_depth']},
            memory_summary={'topic_stack': [], 'current_topic': 'Redis', 'followup_depth': 0},
        )
        self.engine = CompositeV3InterviewAgentEngine()

    @patch('interviews.agent.search_knowledge_context')
    def test_prepare_graph_records_v3_decision_nodes(self, search_mock):
        search_mock.return_value = {'contexts': [], 'retrieval_trace': {}, 'retrieval_explanation': {}}
        answer = '我负责Redis缓存模块，实现了旁路缓存并监控命中率，最终数据库查询量下降了35%。'
        question = InterviewQuestion.objects.create(
            session=self.session,
            sequence=1,
            question_text='请说明你在缓存项目中的个人贡献？',
            answer_text=answer,
            answered_at=timezone.now(),
            question_plan={
                'stage': InterviewSession.InterviewStage.PROJECT_DEEP_DIVE,
                'target_stage': InterviewSession.InterviewStage.PROJECT_DEEP_DIVE,
                'target_dimension': 'technical_depth',
                'topic_id': 'Redis',
                'followup_depth': 0,
            },
            target_dimension='technical_depth',
        )
        state = self.engine.prepare_submit_answer_turn(
            session=self.session,
            current_question=question,
            answer_text=answer,
            user=self.user,
            answered_count=1,
            history=[{'sequence': 1, 'question': question.question_text, 'answer': answer, 'evaluation': {}}],
            resume_text='',
            jd_text='',
            media_context={},
        )
        self.assertIn('evaluate_evidence', state.node_order)
        self.assertIn('decide_termination', state.node_order)
        self.assertIn('select_next_action', state.node_order)
        self.assertIn('plan_transition', state.node_order)
        self.assertFalse(state.interview_finished)
        question.refresh_from_db()
        self.assertIn('answer_evidence_profile', question.ai_feedback)

    def test_weak_answer_clarifies_instead_of_escalating(self):
        evidence = self.engine._node_evaluate_evidence({
            'answer_text': '我用过Redis。',
            'answer_evaluation': {'final_score': 38, 'confidence': 0.7, 'evidence_items': []},
        })
        action = self.engine._node_select_next_action({
            'session_id': str(self.session.id),
            'answer_state': evidence['answer_state'],
            'termination_decision': {'continue_interview': True, 'mandatory_gaps': ['technical_depth'], 'optional_gaps': [], 'reason': 'continue_coverage'},
            'followup_depth': 0,
            'current_question_plan': {'target_dimension': 'technical_depth', 'topic_id': 'Redis'},
            'current_topic': 'Redis',
            'answer_evaluation': {},
        })
        self.assertEqual(evidence['answer_state'], 'insufficient')
        self.assertEqual(action['next_action'], 'CLARIFY')

    def test_strong_answer_is_challenged_with_a_grounded_bridge(self):
        answer = '我负责Redis缓存设计，比较了旁路缓存和写穿方案的取舍，命中率提升到92%，并处理了缓存一致性边界。'
        evidence = self.engine._node_evaluate_evidence({
            'answer_text': answer,
            'answer_evaluation': {
                'final_score': 90, 'depth_score': 92, 'relevance_score': 90, 'confidence': 0.9,
                'evidence_items': [{'quote': '命中率提升到92%', 'supported': True}, {'quote': '处理了缓存一致性边界', 'supported': True}],
            },
        })
        action = self.engine._node_select_next_action({
            'session_id': str(self.session.id),
            'answer_state': evidence['answer_state'],
            'termination_decision': {'continue_interview': True, 'mandatory_gaps': ['technical_depth'], 'optional_gaps': [], 'reason': 'continue_coverage'},
            'followup_depth': 1,
            'current_question_plan': {'target_dimension': 'technical_depth', 'topic_id': 'Redis'},
            'current_topic': 'Redis',
            'answer_evaluation': {'follow_up_target': '验证缓存一致性边界'},
        })
        turn = self.engine._node_plan_transition({
            'next_action': action['next_action'],
            'question_plan': action['question_plan'],
            'answer_text': answer,
        })
        safe_question = self.engine._safe_question({'question_plan': turn['question_plan']})
        self.assertEqual(evidence['answer_state'], 'strong')
        self.assertEqual(action['next_action'], 'CHALLENGE')
        self.assertIn('Redis', turn['dialogue_turn_plan']['answer_reference'])
        self.assertIn('Redis', safe_question)

    def test_adjacent_stage_transition_is_not_rejected(self):
        state = {
            'session_id': str(self.session.id),
            'question_plan': {
                'stage': 'project_deep_dive',
                'target_stage': 'fundamentals_probe',
                'next_action': 'PROBE',
                'answer_reference': 'Redis',
            },
            'rag_context': [],
        }
        errors = self.engine._validate_v2_question(state, '你刚才提到“Redis”，它在缓存一致性方面有哪些边界？')
        self.assertNotIn('stage_mismatch', errors)

    def test_multi_question_without_bridge_routes_directly_to_safe_fallback(self):
        route = self.engine._route_validation({
            'state': {
                'validation_errors': ['multiple_questions', 'missing_answer_bridge'],
                'generation_attempt': 0,
            },
        })
        self.assertEqual(route, 'fallback')

    def test_safe_fallback_for_adjacent_stage_is_valid(self):
        state = {
            'session_id': str(self.session.id),
            'answered_count': 1,
            'question_plan': {
                'stage': 'project_deep_dive',
                'target_stage': 'fundamentals_probe',
                'next_action': 'PROBE',
                'answer_reference': 'Redis',
                'target_dimension': 'technical_depth',
            },
            'rag_context': [],
        }
        question = self.engine._safe_question(state)
        self.assertEqual(self.engine._validate_v2_question(state, question), [])
        self.assertEqual(question.count('？') + question.count('?'), 1)
        self.assertIn('Redis', question)

        delta = self.engine._node_safe_fallback({
            **state,
            'validation_errors': ['multiple_questions', 'missing_answer_bridge'],
        })
        self.assertEqual(delta['fallback_reason'], 'structural_validation_fallback')

    def test_dynamic_interview_can_continue_beyond_legacy_question_count_and_ten_turns(self):
        decision = self.engine._node_decide_termination({
            'session_id': str(self.session.id),
            'answered_count': 11,
            'coverage_summary': {'coverage': {}, 'coverage_gaps': ['technical_depth']},
            'answer_state': 'partial',
        })
        self.assertTrue(decision['termination_decision']['continue_interview'])
        self.assertFalse(decision['interview_finished'])

    def test_realistic_question_serializer_hides_internal_evaluation(self):
        question = InterviewQuestion.objects.create(
            session=self.session,
            sequence=1,
            question_text='请介绍项目。',
            ai_feedback={'final_score': 80},
            rag_context=[{'chunk_id': 'private'}],
            question_plan={'next_action': 'PROBE'},
            target_dimension='technical_depth',
        )
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=self.user)
        data = InterviewQuestionSerializer(question, context={'request': request}).data
        self.assertIsNone(data['ai_feedback'])
        self.assertEqual(data['rag_context'], [])
        self.assertEqual(data['question_plan'], {})


class AgentToolExecutorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tool-v2', email='tool-v2@example.com', password='pass')
        self.other = User.objects.create_user(username='tool-v2-other', email='tool-v2-other@example.com', password='pass')
        self.session = InterviewSession.objects.create(user=self.user, job_position='后端开发')

    def test_executor_rejects_invalid_input_schema_before_handler(self):
        registry = AgentToolRegistry()
        registry.register(AgentToolSpec(
            name='test.schema',
            subagent_name='SafetyAgent',
            input_schema={'type': 'object', 'required': ['question']},
            permission_scope='session_owner',
            handler=lambda **kwargs: {'ok': True},
        ))

        result = AgentToolExecutor(registry).execute('test.schema', user=self.user, session=self.session, payload={})

        self.assertFalse(result.ok)
        self.assertIn('input_schema_invalid', result.error)

    def test_executor_denies_non_owner(self):
        registry = AgentToolRegistry()
        registry.register(AgentToolSpec(
            name='test.private',
            subagent_name='RetrievalAgent',
            permission_scope='session_owner',
            handler=lambda **kwargs: {'ok': True},
        ))

        result = AgentToolExecutor(registry).execute('test.private', user=self.other, session=self.session, payload={})

        self.assertFalse(result.ok)
        self.assertEqual(result.error, 'tool_permission_denied')

    def test_only_idempotent_tool_retries(self):
        calls = {'count': 0}

        def flaky(**kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                raise RuntimeError('temporary_failure')
            return {'value': 1}

        registry = AgentToolRegistry()
        registry.register(AgentToolSpec(
            name='test.retry',
            subagent_name='RetrievalAgent',
            permission_scope='session_owner',
            handler=flaky,
            idempotent=True,
            max_retries=1,
        ))

        result = AgentToolExecutor(registry).execute('test.retry', user=self.user, session=self.session, payload={})

        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(calls['count'], 2)
