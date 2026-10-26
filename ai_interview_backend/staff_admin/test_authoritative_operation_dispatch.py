import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AsyncOperation, OperationDispatchOutbox
from core.operations import create_operation, request_operation_retry
from core.task_registry import register_operation, retry_legacy_operation_source
from interviews.models import (
    EvaluationDataset,
    EvaluationRun,
    InterviewAgentDispatch,
    InterviewAgentExecution,
    InterviewSession,
)
from knowledge.models import KnowledgeDocument, KnowledgeDocumentRevision
from users.models import User

from .models import StaffAccount, StaffRole


class StaffDurableCommandTests(TestCase):
    def setUp(self):
        role = StaffRole.objects.create(slug='durable-ops', name='Durable Ops', permissions=['*'])
        self.staff = StaffAccount.objects.create_account(
            email='durable-admin@example.com',
            password='staff-pass-123',
            display_name='Durable Admin',
            status=StaffAccount.Status.ACTIVE,
        )
        self.staff.roles.add(role)
        self.owner = User.objects.create_user(
            username='knowledge-owner',
            email='knowledge-owner@example.com',
            password='pass12345',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _published_document(self):
        document = KnowledgeDocument.objects.create(
            title='Durable knowledge',
            content='Database-owned input.',
            created_by=self.owner,
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
            parse_status=KnowledgeDocument.ParseStatus.PARSED,
        )
        revision = KnowledgeDocumentRevision.objects.create(
            document=document,
            version_number=1,
            status=KnowledgeDocumentRevision.Status.PUBLISHED,
            source_content=document.content,
            created_by=self.owner,
            published_at=timezone.now(),
        )
        document.draft_revision = revision
        document.published_revision = revision
        document.save(update_fields=['draft_revision', 'published_revision', 'updated_at'])
        return document, revision

    def test_knowledge_reindex_creates_operation_and_identifier_only_dispatch(self):
        document, revision = self._published_document()

        response = self.client.post(
            f'/api/admin/v1/knowledge-documents/{document.pk}/reindex/',
            {'operation_reason': '验证知识索引通过统一 Operation 投递。'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='knowledge-reindex-operation',
        )

        self.assertEqual(response.status_code, 202)
        operation = AsyncOperation.objects.get(pk=response.data['operation_id'])
        self.assertEqual(operation.operation_type, 'knowledge.reindex')
        self.assertEqual(operation.user, self.owner)
        self.assertEqual(operation.input_version, str(revision.pk))
        dispatch = OperationDispatchOutbox.objects.get(operation=operation)
        self.assertEqual(dispatch.payload, {'operation_id': str(operation.pk)})
        self.assertEqual(response['X-Operation-Id'], str(operation.pk))

    def test_global_search_rebuild_requires_and_reuses_linked_admin_principal(self):
        principal = User.objects.create_user(
            username='durable-admin-principal',
            email=self.staff.email,
            password='pass12345',
            role=User.Role.ADMIN,
        )
        payload = {'operation_reason': '验证公共搜索重建走持久命令 Outbox。'}

        first = self.client.post(
            '/api/admin/v1/content/operations/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='community-search-rebuild-once',
        )
        second = self.client.post(
            '/api/admin/v1/content/operations/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='community-search-rebuild-once',
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data['operation_id'], second.data['operation_id'])
        operation = AsyncOperation.objects.get(pk=first.data['operation_id'])
        self.assertEqual(operation.user, principal)
        self.assertEqual(operation.operation_type, 'community.search_rebuild')
        self.assertEqual(
            OperationDispatchOutbox.objects.filter(operation=operation).count(),
            1,
        )

    def test_staff_offline_evaluation_uses_registered_operation_handler(self):
        principal = User.objects.create_user(
            username='evaluation-admin-principal',
            email=self.staff.email,
            password='pass12345',
            role=User.Role.ADMIN,
        )
        dataset = EvaluationDataset.objects.create(
            name='Staff evaluation dataset',
            created_by=principal,
        )

        response = self.client.post(
            '/api/admin/v1/interview-config/runs/',
            {
                'dataset_id': dataset.pk,
                'operation_reason': '验证管理端离线评估进入统一 Operation。',
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='staff-evaluation-operation',
        )

        self.assertEqual(response.status_code, 202)
        operation = AsyncOperation.objects.get(pk=response.data['operation_id'])
        run = EvaluationRun.objects.get(pk=response.data['id'])
        self.assertEqual(operation.operation_type, 'interview.evaluation')
        self.assertEqual(operation.user, principal)
        self.assertEqual(run.operation, operation)
        self.assertEqual(run.created_by, principal)
        self.assertEqual(
            OperationDispatchOutbox.objects.get(operation=operation).payload,
            {'operation_id': str(operation.pk)},
        )


class LegacyOperationCompatibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='legacy-operation-owner',
            email='legacy-operation@example.com',
            password='pass12345',
        )

    def test_projection_is_create_once_and_does_not_overwrite_authoritative_status(self):
        first = register_operation(
            user=self.user,
            operation_type='legacy.test',
            source_app='legacy',
            source_model='Input',
            source_id='one',
            title='Legacy projection',
            status='failed',
            error_message='original failure',
            retryable=True,
        )
        second = register_operation(
            user=self.user,
            operation_type='legacy.test',
            source_app='legacy',
            source_model='Input',
            source_id='one',
            title='Mutable domain state',
            status='processing',
            progress=80,
        )

        first.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, AsyncOperation.Status.FAILED)
        self.assertEqual(first.error_message, 'original failure')
        self.assertEqual(AsyncOperation.objects.filter(user=self.user).count(), 1)

    def _agent_operation(self, *, operation_status=AsyncOperation.Status.FAILED,
                         execution_status=InterviewAgentExecution.Status.FAILED_TERMINAL):
        session = InterviewSession.objects.create(user=self.user, job_position='Backend Engineer')
        operation = create_operation(
            user=self.user,
            operation_type='interview.agent_turn',
            source_app='interviews',
            source_model='InterviewAgentExecution',
            source_id='placeholder',
            title='Agent turn',
            input_type='InterviewAgentExecution',
            input_id='placeholder',
        )
        AsyncOperation.objects.filter(pk=operation.pk).update(
            status=operation_status,
            completed_at=timezone.now() if operation_status in {
                AsyncOperation.Status.FAILED,
                AsyncOperation.Status.CANCELED,
            } else None,
            cancel_requested_at=(
                timezone.now() if operation_status == AsyncOperation.Status.CANCELED else None
            ),
            error_code='agent_failed',
            retryable=operation_status == AsyncOperation.Status.FAILED,
        )
        execution = InterviewAgentExecution.objects.create(
            operation=operation,
            session=session,
            thread_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event='answer_submitted',
            idempotency_key='agent-retry',
            request_hash='a' * 64,
            status=execution_status,
            version=3,
            fencing_token=7,
            lease_owner='stale-worker',
            lease_expires_at=timezone.now(),
            heartbeat_at=timezone.now(),
            error_code='provider_timeout',
            fallback_reason='retry exhausted',
            completed_at=timezone.now(),
        )
        AsyncOperation.objects.filter(pk=operation.pk).update(
            source_id=str(execution.pk),
            input_id=str(execution.pk),
        )
        operation.refresh_from_db()
        dispatch = InterviewAgentDispatch.objects.create(
            execution=execution,
            status=InterviewAgentDispatch.Status.FAILED,
            attempts=4,
            celery_task_id='stale-task',
            error_code='broker_timeout',
            error_message='stale error',
            published_at=timezone.now(),
        )
        return operation, execution, dispatch

    def test_agent_retry_resets_execution_and_dedicated_dispatch_with_new_fence(self):
        operation, execution, dispatch = self._agent_operation()
        operation = request_operation_retry(
            operation.pk,
            user=self.user,
            dispatch_retry=False,
        )

        forwarded = retry_legacy_operation_source(operation)

        execution.refresh_from_db()
        dispatch.refresh_from_db()
        self.assertEqual(forwarded.pk, operation.pk)
        self.assertEqual(execution.status, InterviewAgentExecution.Status.FAILED_RETRYABLE)
        self.assertIsNone(execution.completed_at)
        self.assertEqual(execution.error_code, '')
        self.assertEqual(execution.lease_owner, '')
        self.assertIsNone(execution.lease_expires_at)
        self.assertEqual(execution.fencing_token, 8)
        self.assertEqual(dispatch.status, InterviewAgentDispatch.Status.PENDING)
        self.assertEqual(dispatch.attempts, 0)
        self.assertEqual(dispatch.celery_task_id, '')

    def test_canceled_agent_operation_cannot_be_revived(self):
        operation, execution, dispatch = self._agent_operation(
            operation_status=AsyncOperation.Status.CANCELED,
            execution_status=InterviewAgentExecution.Status.CANCELED,
        )

        with self.assertRaisesMessage(ValueError, 'agent_operation_canceled'):
            retry_legacy_operation_source(operation)

        execution.refresh_from_db()
        dispatch.refresh_from_db()
        self.assertEqual(execution.status, InterviewAgentExecution.Status.CANCELED)
        self.assertEqual(dispatch.status, InterviewAgentDispatch.Status.FAILED)
