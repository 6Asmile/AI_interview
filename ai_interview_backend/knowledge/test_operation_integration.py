from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase

from core.models import AsyncOperation, OperationDispatchOutbox
from core.tasks import execute_operation
from users.models import User

from .models import KnowledgeDocument, KnowledgeImportBatch, KnowledgeImportFile
from .operation_handlers import IMPORT_OPERATION, REINDEX_OPERATION, create_knowledge_operation


class KnowledgeOperationIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='knowledge-operation-owner',
            email='knowledge-operation-owner@example.com',
            password='pass12345',
        )

    def test_operation_and_minimal_dispatch_rollback_together(self):
        operation_id = None
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                operation = create_knowledge_operation(
                    user=self.owner,
                    operation_type=REINDEX_OPERATION,
                    source_model='KnowledgeDocument',
                    source_id='missing-document',
                    input_version='revision-v1',
                    title='rollback-test',
                )
                operation_id = operation.pk
                dispatch = operation.dispatches.get()
                self.assertEqual(dispatch.payload, {'operation_id': str(operation.pk)})
                self.assertEqual(dispatch.task_name, 'core.tasks.execute_operation')
                raise RuntimeError('force-domain-transaction-rollback')

        self.assertFalse(AsyncOperation.objects.filter(pk=operation_id).exists())
        self.assertFalse(OperationDispatchOutbox.objects.filter(operation_id=operation_id).exists())

    def test_worker_reloads_authorization_and_rejects_changed_ownership(self):
        document = KnowledgeDocument.objects.create(
            title='private-document',
            content='private content',
            created_by=self.owner,
        )
        operation = create_knowledge_operation(
            user=self.owner,
            operation_type=REINDEX_OPERATION,
            source_model='KnowledgeDocument',
            source_id=document.pk,
            title='authorization-reload-test',
        )
        replacement_owner = User.objects.create_user(
            username='knowledge-replacement-owner',
            email='knowledge-replacement-owner@example.com',
            password='pass12345',
        )
        document.created_by = replacement_owner
        document.save(update_fields=['created_by', 'updated_at'])

        result = execute_operation.run(str(operation.pk))

        operation.refresh_from_db()
        self.assertEqual(result['error_code'], 'knowledge_input_forbidden')
        self.assertEqual(operation.status, AsyncOperation.Status.FAILED)

    def test_duplicate_delivery_reuses_imported_document(self):
        document = KnowledgeDocument.objects.create(
            title='already-imported',
            content='stable result',
            created_by=self.owner,
        )
        batch = KnowledgeImportBatch.objects.create(
            uploaded_by=self.owner,
            total_files=1,
        )
        import_file = KnowledgeImportFile.objects.create(
            batch=batch,
            source_file=SimpleUploadedFile('stable.txt', b'stable result'),
            original_name='stable.txt',
            status=KnowledgeImportFile.Status.IMPORTED,
            document=document,
        )
        operation = create_knowledge_operation(
            user=self.owner,
            operation_type=IMPORT_OPERATION,
            source_model='KnowledgeImportFile',
            source_id=import_file.pk,
            title='duplicate-delivery-test',
        )

        first = execute_operation.run(str(operation.pk))
        second = execute_operation.run(str(operation.pk))

        self.assertEqual(first['status'], AsyncOperation.Status.SUCCEEDED)
        self.assertTrue(second['idempotent_replay'])
        self.assertEqual(second['result_id'], str(document.pk))
        self.assertEqual(KnowledgeDocument.objects.filter(pk=document.pk).count(), 1)
