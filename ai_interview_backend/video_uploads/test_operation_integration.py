from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import AsyncOperation, OperationDispatchOutbox
from core.tasks import execute_operation
from users.models import User

from .models import FileUploadTask
from .operation_handlers import create_video_operation


class VideoOperationIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='video-operation-user',
            email='video-operation-user@example.com',
            password='pass12345',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.upload = FileUploadTask.objects.create(
            user=self.user,
            file_identifier='a' * 64,
            file_name='interview.mp4',
            file_size=1024,
            total_chunks=1,
            uploaded_chunks=1,
            status=FileUploadTask.Status.COMPLETED,
        )

    @patch('video_uploads.views.admit_expensive_operation')
    def test_merge_rejects_missing_idempotency_key(self, _admit):
        response = self.client.post(
            '/api/v1/merge/',
            {'task_id': str(self.upload.pk), 'enable_transcode': False},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'idempotency_key_required')
        self.assertFalse(AsyncOperation.objects.filter(source_app='video_uploads').exists())
        _admit.assert_not_called()

    @patch('video_uploads.views.admit_expensive_operation')
    def test_merge_creates_operation_and_minimal_dispatch(self, _admit):
        response = self.client.post(
            '/api/v1/merge/',
            {'task_id': str(self.upload.pk), 'enable_transcode': False},
            format='json',
            HTTP_IDEMPOTENCY_KEY='video-merge-operation',
        )

        self.assertEqual(response.status_code, 202)
        operation = AsyncOperation.objects.get(pk=response.data['operation_id'])
        dispatch = operation.dispatches.get()
        self.assertEqual(dispatch.payload, {'operation_id': str(operation.pk)})
        self.assertEqual(response.data['merge_task_id'], str(operation.pk))
        self.assertEqual(response['X-Operation-Id'], str(operation.pk))

    def test_operation_and_dispatch_rollback_with_domain_transaction(self):
        operation_id = None
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                operation = create_video_operation(user=self.user, upload_task=self.upload)
                operation_id = operation.pk
                self.assertEqual(
                    operation.dispatches.get().payload,
                    {'operation_id': str(operation.pk)},
                )
                raise RuntimeError('force-media-transaction-rollback')

        self.assertFalse(AsyncOperation.objects.filter(pk=operation_id).exists())
        self.assertFalse(OperationDispatchOutbox.objects.filter(operation_id=operation_id).exists())

    @patch('video_uploads.operation_handlers.merge_chunks_task.run')
    def test_duplicate_delivery_executes_merge_once(self, merge_run):
        merge_run.return_value = {'success': True, 'merged_file': 'synthetic-output.mp4'}
        operation = create_video_operation(user=self.user, upload_task=self.upload)

        first = execute_operation.run(str(operation.pk))
        second = execute_operation.run(str(operation.pk))

        self.assertEqual(first['status'], AsyncOperation.Status.SUCCEEDED)
        self.assertTrue(second['idempotent_replay'])
        merge_run.assert_called_once_with(str(self.upload.pk))

    @patch('video_uploads.operation_handlers.merge_chunks_task.run')
    def test_worker_reloads_owner_before_processing(self, merge_run):
        operation = create_video_operation(user=self.user, upload_task=self.upload)
        other = User.objects.create_user(
            username='video-new-owner',
            email='video-new-owner@example.com',
            password='pass12345',
        )
        self.upload.user = other
        self.upload.save(update_fields=['user', 'updated_at'])

        result = execute_operation.run(str(operation.pk))

        self.assertEqual(result['error_code'], 'media_input_forbidden')
        merge_run.assert_not_called()
