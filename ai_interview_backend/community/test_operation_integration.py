from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AsyncOperation
from core.tasks import execute_operation
from users.models import User

from .models import CommunityContent, ModerationCase
from .operation_handlers import create_search_rebuild_operation
from .services import create_revision, submit_content


class CommunityOperationIntegrationTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username='community-operation-author',
            email='community-operation-author@example.com',
            password='pass12345',
        )

    @patch(
        'community.operation_handlers.create_operation_with_dispatch',
        side_effect=RuntimeError('dispatch-row-create-failed'),
    )
    def test_moderation_domain_change_rolls_back_when_dispatch_creation_fails(self, _create):
        content = CommunityContent.objects.create(
            author=self.author,
            content_type=CommunityContent.ContentType.EXPERIENCE,
            title='transactional publish',
        )
        create_revision(
            content=content,
            author=self.author,
            title=content.title,
            body='review this immutable revision',
        )

        with self.assertRaisesRegex(RuntimeError, 'dispatch-row-create-failed'):
            submit_content(content=content, user=self.author)

        content.refresh_from_db()
        self.assertEqual(content.status, CommunityContent.Status.DRAFT)
        self.assertFalse(ModerationCase.objects.filter(content=content).exists())
        self.assertFalse(AsyncOperation.objects.filter(source_app='community').exists())

    @patch('community.operation_handlers.inspect_and_redact')
    def test_moderation_freezes_revision_and_duplicate_delivery_is_idempotent(self, inspect):
        content = CommunityContent.objects.create(
            author=self.author,
            content_type=CommunityContent.ContentType.EXPERIENCE,
            title='old revision',
        )
        old_revision = create_revision(
            content=content,
            author=self.author,
            title='old revision',
            body='old body requiring review',
        )
        submitted = submit_content(content=content, user=self.author)
        operation = submitted._accepted_operation
        case = ModerationCase.objects.get(content=content, revision=old_revision)
        new_revision = create_revision(
            content=content,
            author=self.author,
            title='new revision',
            body='clean replacement body',
        )
        content.refresh_from_db()
        expected_new_risk = content.risk_level
        inspect.return_value = ('redacted old body', [{'type': 'test'}], 'high')

        first = execute_operation.run(str(operation.pk))
        second = execute_operation.run(str(operation.pk))

        case.refresh_from_db()
        content.refresh_from_db()
        self.assertEqual(first['status'], AsyncOperation.Status.SUCCEEDED)
        self.assertTrue(second['idempotent_replay'])
        inspect.assert_called_once_with(old_revision.body)
        self.assertEqual(case.risk_level, 'high')
        self.assertEqual(content.current_revision_id, new_revision.pk)
        self.assertEqual(content.risk_level, expected_new_risk)
        self.assertEqual(operation.dispatches.get().payload, {'operation_id': str(operation.pk)})

    @patch('community.tasks.rebuild_public_search_indexes.run')
    def test_search_handler_reloads_staff_permission(self, rebuild):
        staff = User.objects.create_user(
            username='community-search-staff',
            email='community-search-staff@example.com',
            password='pass12345',
            is_staff=True,
        )
        operation = create_search_rebuild_operation(user=staff)
        staff.is_staff = False
        staff.role = User.Role.CANDIDATE
        staff.save(update_fields=['is_staff', 'role', 'updated_at'])

        result = execute_operation.run(str(operation.pk))

        self.assertEqual(result['error_code'], 'community_search_rebuild_forbidden')
        rebuild.assert_not_called()

    @patch('community.views.admit_expensive_operation')
    def test_search_rebuild_requires_idempotency_and_returns_operation_envelope(self, _admit):
        staff = User.objects.create_user(
            username='community-search-api-staff',
            email='community-search-api-staff@example.com',
            password='pass12345',
            is_staff=True,
            date_joined=timezone.now() - timedelta(days=30),
        )
        client = APIClient()
        client.force_authenticate(staff)

        missing = client.post('/api/v1/community/index-status/', {}, format='json')
        accepted = client.post(
            '/api/v1/community/index-status/',
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='community-search-rebuild-v1',
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.data['code'], 'idempotency_key_required')
        self.assertEqual(accepted.status_code, 202)
        operation = AsyncOperation.objects.get(pk=accepted.data['operation_id'])
        self.assertEqual(operation.dispatches.get().payload, {'operation_id': str(operation.pk)})
        self.assertEqual(accepted.data['task_id'], str(operation.pk))
        self.assertEqual(accepted['X-Operation-Id'], str(operation.pk))
