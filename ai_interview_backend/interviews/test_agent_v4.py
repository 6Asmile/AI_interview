import json
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.test import APIClient

from users.models import User

from .agent import get_interview_agent_engine
from .agent_v4.contracts import AgentEvent, AgentTurnInput, EvidenceItem, QuestionPlan
from .agent_v4.engine import CompositeV4InterviewAgentEngine
from .models import (
    InterviewAgentDispatch,
    InterviewAgentExecution,
    InterviewAgentNodeRun,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewSession,
)
from .tasks import run_composite_v4_turn


class AgentV4ContractTests(SimpleTestCase):
    def valid_turn(self):
        return {
            'session_id': uuid4(),
            'question_id': 1,
            'user_id': 1,
            'event': AgentEvent.SUBMIT_ANSWER,
            'answer_text': '我负责缓存一致性方案，并通过监控验证了结果。',
            'answered_count': 1,
            'history': [],
            'resume_text': '',
            'jd_text': '',
            'media_context': {},
        }

    def test_turn_contract_rejects_unknown_fields(self):
        payload = {**self.valid_turn(), 'api_key': 'must-not-enter-state'}
        with self.assertRaises(ValidationError):
            AgentTurnInput.model_validate(payload)

    def test_turn_contract_accepts_uuid_and_enum_from_json_transport(self):
        payload = self.valid_turn()
        encoded = json.dumps({
            **payload,
            'session_id': str(payload['session_id']),
            'event': payload['event'].value,
        }, ensure_ascii=False)

        parsed = AgentTurnInput.model_validate_json(encoded)

        self.assertEqual(parsed.session_id, payload['session_id'])
        self.assertEqual(parsed.event, AgentEvent.SUBMIT_ANSWER)

    def test_worker_rejects_unimplemented_events_before_business_writes(self):
        payload = {
            **self.valid_turn(),
            'session_id': str(self.valid_turn()['session_id']),
            'event': AgentEvent.REGENERATE_QUESTION.value,
        }

        with self.assertRaisesMessage(ValueError, 'unsupported_agent_event'):
            run_composite_v4_turn.run(payload)

    def test_rag_evidence_requires_real_chunk_id(self):
        with self.assertRaises(ValidationError):
            EvidenceItem.model_validate({
                'source': 'rag', 'quote': '缓存一致性', 'supported': True, 'chunk_id': None,
            })

    def test_question_plan_cannot_attach_sources_when_rag_is_disabled(self):
        with self.assertRaises(ValidationError):
            QuestionPlan.model_validate({
                'target_stage': 'technical_deep_dive',
                'target_dimension': 'technical_depth',
                'target_gap': '缓存一致性',
                'difficulty': 'medium',
                'next_action': 'PROBE',
                'use_rag': False,
                'rag_source_ids': ['other-tenant-chunk'],
            })

    @override_settings(INTERVIEW_AGENT_ENGINE='composite_v4')
    def test_engine_switch(self):
        self.assertIsInstance(get_interview_agent_engine(), CompositeV4InterviewAgentEngine)


class AgentV4ExecutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='agent-v4-user', email='agent-v4@example.com', password='test-password',
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            sequence=1,
            question_text='请介绍你负责的一个真实项目。',
        )

    def test_business_execution_maps_to_langgraph_identifiers_idempotently(self):
        engine = CompositeV4InterviewAgentEngine()
        first = engine._get_or_create_run(
            session=self.session,
            question=self.question,
            answer_text='我负责订单缓存模块。',
            event='submit_answer_stream',
        )
        second = engine._get_or_create_run(
            session=self.session,
            question=self.question,
            answer_text='我负责订单缓存模块。',
            event='submit_answer_stream',
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(InterviewAgentExecution.objects.count(), 1)
        execution = InterviewAgentExecution.objects.get()
        self.assertEqual(execution.thread_id, self.session.id)
        self.assertEqual(execution.run_id, first.id)
        self.assertNotIn('answer', execution.__dict__)

    @patch('interviews.agent.search_knowledge_context')
    @patch('interviews.agent_v2.resolve_ai_config')
    def test_prepare_turn_runs_real_postgres_checkpoint_graph(self, resolve_config, search):
        resolve_config.return_value = SimpleNamespace(api_key='', model=None, source='unavailable')
        search.return_value = {
            'contexts': [],
            'retrieval_trace': {'fallback_reason': 'no_approved_rag_context'},
            'retrieval_explanation': {'fallback_reason': 'no_approved_rag_context'},
        }
        self.question.answer_text = '我负责订单缓存模块，设计旁路缓存并补充了命中率监控。'
        self.question.question_plan = {
            'target_dimension': 'technical_depth',
            'target_stage': 'project_deep_dive',
        }
        self.question.save(update_fields=['answer_text', 'question_plan'])

        state = CompositeV4InterviewAgentEngine().prepare_submit_answer_turn(
            session=self.session,
            current_question=self.question,
            answer_text=self.question.answer_text,
            user=self.user,
            answered_count=1,
            history=[{
                'question': self.question.question_text,
                'answer': self.question.answer_text,
                'evaluation': {},
            }],
            resume_text='',
            jd_text='',
            media_context={},
        )

        execution = InterviewAgentExecution.objects.get(run_id=state.agent_run_id)
        self.assertEqual(execution.status, InterviewAgentExecution.Status.EVALUATED)
        self.assertEqual(state.answer_evaluation['evaluation_mode'], 'rule_only_degraded')

    @patch('interviews.agent.search_knowledge_context')
    @patch('interviews.agent_v2.resolve_ai_config')
    def test_completed_prepare_checkpoint_replays_without_rerunning_nodes(self, resolve_config, search):
        resolve_config.return_value = SimpleNamespace(api_key='', model=None, source='unavailable')
        search.return_value = {
            'contexts': [],
            'retrieval_trace': {'fallback_reason': 'no_approved_rag_context'},
            'retrieval_explanation': {'fallback_reason': 'no_approved_rag_context'},
        }
        self.question.answer_text = '我负责订单缓存模块，并为命中率和回源延迟补充了监控。'
        self.question.question_plan = {
            'target_dimension': 'technical_depth',
            'target_stage': 'project_deep_dive',
        }
        self.question.save(update_fields=['answer_text', 'question_plan'])
        kwargs = {
            'session': self.session,
            'current_question': self.question,
            'answer_text': self.question.answer_text,
            'user': self.user,
            'answered_count': 1,
            'history': [{
                'question': self.question.question_text,
                'answer': self.question.answer_text,
                'evaluation': {},
            }],
            'resume_text': '',
            'jd_text': '',
            'media_context': {},
        }
        engine = CompositeV4InterviewAgentEngine()

        first = engine.prepare_submit_answer_turn(**kwargs)
        first_node_count = InterviewAgentNodeRun.objects.filter(run_id=first.agent_run_id).count()
        second = engine.prepare_submit_answer_turn(**kwargs)

        self.assertEqual(first.agent_run_id, second.agent_run_id)
        self.assertEqual(
            InterviewAgentNodeRun.objects.filter(run_id=first.agent_run_id).count(),
            first_node_count,
        )
        self.assertEqual(first.answer_evaluation, second.answer_evaluation)


@override_settings(INTERVIEW_AGENT_ENGINE='default')
class DurableSubmissionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='durable-submit', email='durable-submit@example.com', password='test-password',
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            job_position='后端开发',
            status=InterviewSession.Status.RUNNING,
            started_at=timezone.now(),
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            sequence=1,
            question_text='请介绍你负责的一个项目。',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_async_submission_persists_answer_execution_job_and_outbox_atomically(self):
        response = self.client.post(
            f'/api/v1/interviews/{self.session.id}/submit-answer-stream/?async=true',
            {'question_id': self.question.id, 'answer_text': '我负责订单缓存和故障降级。'},
            format='json',
            HTTP_PREFER='respond-async',
            HTTP_IDEMPOTENCY_KEY='answer-1',
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.question.refresh_from_db()
        self.assertTrue(self.question.answered_at)
        execution = InterviewAgentExecution.objects.get(trigger_question=self.question)
        self.assertEqual(execution.status, InterviewAgentExecution.Status.ANSWER_PERSISTED)
        self.assertEqual(str(execution.run_id), response.data['run_id'])
        self.assertTrue(InterviewAgentDispatch.objects.filter(execution=execution).exists())
        self.assertTrue(InterviewQuestionGenerationJob.objects.filter(
            session=self.session,
            answered_question=self.question,
            status=InterviewQuestionGenerationJob.Status.PENDING,
        ).exists())

    def test_resume_state_uses_postgresql_without_agent_stream(self):
        submit = self.client.post(
            f'/api/v1/interviews/{self.session.id}/submit-answer-stream/?async=true',
            {'question_id': self.question.id, 'answer_text': '我负责订单缓存和故障降级。'},
            format='json',
            HTTP_PREFER='respond-async',
            HTTP_IDEMPOTENCY_KEY='answer-resume',
        )
        self.assertEqual(submit.status_code, 202, submit.data)
        response = self.client.get(f'/api/v1/interviews/{self.session.id}/resume-state/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['resume_action'], 'wait')
        self.assertEqual(response.data['execution']['status'], InterviewAgentExecution.Status.ANSWER_PERSISTED)
        self.assertEqual(response.data['execution']['run_id'], submit.data['run_id'])

    def test_async_idempotency_key_rejects_a_different_payload(self):
        url = f'/api/v1/interviews/{self.session.id}/submit-answer-stream/?async=true'
        first = self.client.post(
            url,
            {'question_id': self.question.id, 'answer_text': '我负责订单缓存和故障降级。'},
            format='json',
            HTTP_PREFER='respond-async',
            HTTP_IDEMPOTENCY_KEY='strict-answer-key',
        )
        second = self.client.post(
            url,
            {'question_id': self.question.id, 'answer_text': '这是一个不同的回答。'},
            format='json',
            HTTP_PREFER='respond-async',
            HTTP_IDEMPOTENCY_KEY='strict-answer-key',
        )
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(second.status_code, 409, second.data)
        self.question.refresh_from_db()
        self.assertEqual(self.question.answer_text, '我负责订单缓存和故障降级。')

    def test_stale_execution_version_cannot_persist_a_question(self):
        submit = self.client.post(
            f'/api/v1/interviews/{self.session.id}/submit-answer-stream/?async=true',
            {'question_id': self.question.id, 'answer_text': '我负责订单缓存和故障降级。'},
            format='json',
            HTTP_PREFER='respond-async',
            HTTP_IDEMPOTENCY_KEY='fenced-answer-key',
        )
        self.assertEqual(submit.status_code, 202, submit.data)
        execution = InterviewAgentExecution.objects.get(trigger_question=self.question)
        state = {
            'session_id': str(self.session.id),
            'run_id': str(execution.run_id),
            'question_plan': {'target_dimension': 'technical_depth'},
            'generated_text': '请说明缓存一致性的具体取舍。',
            'rag_context': [],
            'generation_mode': 'model',
            'answered_count': 1,
            'execution_version': execution.version + 1,
        }
        with self.assertRaisesRegex(RuntimeError, 'execution_fenced_before_question_persist'):
            CompositeV4InterviewAgentEngine()._node_persist(state)
        self.assertEqual(self.session.questions.count(), 1)
