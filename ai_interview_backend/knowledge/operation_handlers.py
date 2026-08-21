"""Durable Operation adapters for knowledge parsing and indexing.

RabbitMQ messages contain only the public Operation UUID.  Every handler
reloads its domain input and authorization context from PostgreSQL before
calling the existing, idempotent domain implementation.
"""

from __future__ import annotations

from django.conf import settings

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import (
    RetryableOperationError,
    TerminalOperationError,
    create_operation_with_dispatch,
)

from .models import KnowledgeDocument, KnowledgeImportFile
from .tasks import process_import_file, reindex_knowledge_document, reparse_knowledge_document


IMPORT_OPERATION = 'knowledge.import'
REPARSE_OPERATION = 'knowledge.reparse'
REINDEX_OPERATION = 'knowledge.reindex'


def create_knowledge_operation(
    *,
    user,
    operation_type: str,
    source_model: str,
    source_id,
    title: str,
    input_version: str = '',
    metadata: dict | None = None,
):
    """Create the Operation and its command intent in the caller transaction."""

    return create_operation_with_dispatch(
        user=user,
        operation_type=operation_type,
        source_app='knowledge',
        source_model=source_model,
        source_id=str(source_id),
        input_type=f'knowledge.{source_model}',
        input_id=str(source_id),
        input_version=str(input_version or ''),
        title=title,
        metadata=metadata or {},
        max_attempts=5,
        queue=settings.CELERY_DOCUMENT_QUEUE,
        routing_key='documents',
    )


def operation_envelope(operation) -> dict:
    return {
        'operation_id': str(operation.pk),
        'status': 'accepted',
        'events_url': f'/api/v2/operations/{operation.pk}/events/',
        'result_url': f'/api/v2/operations/{operation.pk}/',
    }


def _can_access_document(operation, document: KnowledgeDocument) -> bool:
    user = operation.user
    return bool(
        document.created_by_id == operation.user_id
        or user.is_staff
        or getattr(user, 'role', '') in {'admin', 'hr'}
    )


def _retry_or_raise(exc: Exception):
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        raise RetryableOperationError(
            'knowledge_dependency_unavailable',
            str(exc),
            retry_after_seconds=30,
        ) from exc
    raise TerminalOperationError('knowledge_processing_failed', str(exc)) from exc


@register_operation_handler(IMPORT_OPERATION)
def import_knowledge_file(context):
    operation = context.get_operation()
    try:
        import_file = KnowledgeImportFile.objects.select_related('batch').get(pk=operation.input_id)
    except KnowledgeImportFile.DoesNotExist as exc:
        raise TerminalOperationError('knowledge_import_file_not_found') from exc
    if import_file.batch.uploaded_by_id != operation.user_id:
        raise TerminalOperationError('knowledge_input_forbidden')
    if import_file.document_id:
        return OperationHandlerResult(
            result_type='knowledge.KnowledgeDocument',
            result_id=str(import_file.document_id),
            result={'import_file_id': str(import_file.pk)},
        )
    context.raise_if_canceled()
    try:
        document = process_import_file(str(import_file.pk))
    except Exception as exc:  # domain adapters classify before the core state transition
        _retry_or_raise(exc)
    context.heartbeat()
    return OperationHandlerResult(
        result_type='knowledge.KnowledgeDocument',
        result_id=str(document.pk),
        result={'import_file_id': str(import_file.pk)},
    )


@register_operation_handler(REPARSE_OPERATION)
def reparse_document(context):
    operation = context.get_operation()
    try:
        document = KnowledgeDocument.objects.get(pk=operation.input_id)
    except KnowledgeDocument.DoesNotExist as exc:
        raise TerminalOperationError('knowledge_document_not_found') from exc
    if not _can_access_document(operation, document):
        raise TerminalOperationError('knowledge_input_forbidden')
    if not document.source_file:
        raise TerminalOperationError('knowledge_source_file_missing')
    context.raise_if_canceled()
    try:
        result = reparse_knowledge_document.run(str(document.pk))
    except Exception as exc:
        _retry_or_raise(exc)
    context.heartbeat()
    return OperationHandlerResult(
        result_type='knowledge.KnowledgeDocument',
        result_id=str(document.pk),
        result={'parse_status': result.get('status')},
    )


@register_operation_handler(REINDEX_OPERATION)
def reindex_document(context):
    operation = context.get_operation()
    try:
        document = KnowledgeDocument.objects.get(pk=operation.input_id)
    except KnowledgeDocument.DoesNotExist as exc:
        raise TerminalOperationError('knowledge_document_not_found') from exc
    if not _can_access_document(operation, document):
        raise TerminalOperationError('knowledge_input_forbidden')
    context.raise_if_canceled()
    try:
        result = reindex_knowledge_document.run(
            str(document.pk),
            operation.input_version or None,
        )
    except Exception as exc:
        _retry_or_raise(exc)
    context.heartbeat()
    return OperationHandlerResult(
        result_type='knowledge.KnowledgeDocument',
        result_id=str(document.pk),
        result={
            'status': result.get('status'),
            'chunk_count': result.get('chunk_count'),
        },
    )
