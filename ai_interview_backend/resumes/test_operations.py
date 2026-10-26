from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import AsyncOperation, OperationDispatchOutbox
from users.models import User

from .models import Resume, ResumeOperationRequest, ResumeSuggestion, ResumeVersion
from .operation_handlers import handle_resume_suggestion
from .operation_service import create_resume_operation


class ResumeUnifiedOperationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='resume-operation-owner',
            email='resume-operation@example.com',
            password='pass12345',
        )
        self.resume = Resume.objects.create(user=self.user, title='Operation resume')
        self.version = ResumeVersion.objects.create(
            resume=self.resume,
            version_number=1,
            resume_json={'basics': {'name': 'Candidate'}},
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_suggestion_instruction_stays_in_postgres_and_dispatch_only_carries_operation_id(self):
        instruction = 'Rewrite this section using only confirmed evidence.'

        operation, request_snapshot = create_resume_operation(
            user=self.user,
            resume=self.resume,
            operation_type='resume.suggestion',
            title='Generate suggestion',
            base_version=self.version,
            task_key='resume.rewrite_section',
            instruction=instruction,
        )

        request_snapshot.refresh_from_db()
        self.assertEqual(request_snapshot.instruction, instruction)
        self.assertNotIn(instruction, str(operation.metadata))
        self.assertNotIn(instruction, operation.input_hash)
        dispatch = OperationDispatchOutbox.objects.get(operation=operation)
        self.assertEqual(dispatch.payload, {'operation_id': str(operation.id)})
        self.assertNotIn(instruction, str(dispatch.payload))

    @patch('resumes.views_v2.admit_expensive_operation')
    def test_same_idempotency_key_creates_one_request_operation_and_dispatch(self, _admit):
        instruction = 'Do not leak this instruction into RabbitMQ.'
        payload = {
            'base_version_id': self.version.pk,
            'task_key': 'resume.rewrite_section',
            'instruction': instruction,
        }
        request_kwargs = {
            'format': 'json',
            'HTTP_IDEMPOTENCY_KEY': 'resume-suggestion-once',
        }

        first = self.client.post(
            f'/api/v2/resumes/{self.resume.pk}/suggestions/',
            payload,
            **request_kwargs,
        )
        replay = self.client.post(
            f'/api/v2/resumes/{self.resume.pk}/suggestions/',
            payload,
            **request_kwargs,
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.data['operation_id'], first.data['operation_id'])
        self.assertEqual(ResumeOperationRequest.objects.count(), 1)
        self.assertEqual(
            AsyncOperation.objects.filter(operation_type='resume.suggestion').count(),
            1,
        )
        dispatch = OperationDispatchOutbox.objects.get(
            operation_id=first.data['operation_id'],
        )
        self.assertEqual(dispatch.payload, {'operation_id': first.data['operation_id']})
        self.assertNotIn(instruction, str(dispatch.payload))

    @patch('resumes.intelligence.generate_resume_suggestion')
    def test_suggestion_handler_reloads_private_snapshot_and_persists_idempotent_result(self, generate):
        instruction = 'Keep the claim factual.'
        operation, request_snapshot = create_resume_operation(
            user=self.user,
            resume=self.resume,
            operation_type='resume.suggestion',
            title='Generate suggestion',
            base_version=self.version,
            task_key='resume.rewrite_section',
            instruction=instruction,
        )
        suggestion = ResumeSuggestion.objects.create(
            resume=self.resume,
            base_version=self.version,
            patch=[{'op': 'replace', 'path': '/basics/summary', 'value': 'Verified summary'}],
            summary='Verified rewrite',
            created_by=self.user,
        )
        generate.return_value = {
            'suggestion': suggestion,
            'questions': [],
            'missing_evidence': [],
            'prompt_hash': 'prompt-hash',
            'config_hash': 'config-hash',
            'envelope_hash': 'envelope-hash',
            'region_tokens': {'task_context': 12},
        }
        context = Mock()
        context.operation = None
        context.get_operation.return_value = operation
        context.heartbeat.return_value = True

        result = handle_resume_suggestion(context)

        generate.assert_called_once_with(
            version=self.version,
            task_key='resume.rewrite_section',
            instruction=instruction,
            job_target_id=None,
        )
        request_snapshot.refresh_from_db()
        self.assertEqual(request_snapshot.result_suggestion, suggestion)
        self.assertIsNotNone(request_snapshot.completed_at)
        self.assertEqual(result.result_id, str(suggestion.pk))
        self.assertEqual(result.result['prompt_hash'], 'prompt-hash')
        context.raise_if_canceled.assert_called()
        self.assertGreaterEqual(context.heartbeat.call_count, 2)

        reused = handle_resume_suggestion(context)
        self.assertTrue(reused.result['reused'])
        generate.assert_called_once()
