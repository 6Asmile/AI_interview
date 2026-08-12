"""Allowlisted durable handlers for community moderation and search."""

from __future__ import annotations

import requests

from django.conf import settings
from django.db import transaction

from core.operation_registry import OperationHandlerResult, register_operation_handler
from core.operations import TerminalOperationError, create_operation_with_dispatch

from .models import CommunityContent, ModerationCase
from .services import inspect_and_redact
from .views import can_manage_community


MODERATION_OPERATION = 'community.moderate'
SEARCH_REBUILD_OPERATION = 'community.search_rebuild'


def create_moderation_operation(*, user, case: ModerationCase):
    return create_operation_with_dispatch(
        user=user,
        operation_type=MODERATION_OPERATION,
        source_app='community',
        source_model='ModerationCase',
        source_id=str(case.pk),
        input_type='community.ModerationCase',
        input_id=str(case.pk),
        input_version=str(case.revision_id),
        input_hash=str(case.revision.body_hash),
        title=f'审核社区内容：{case.content.title}',
        metadata={'content_id': str(case.content_id)},
        max_attempts=3,
        queue=settings.CELERY_COMMUNITY_MODERATION_QUEUE,
        routing_key='community.moderation',
    )


def create_search_rebuild_operation(*, user):
    """Freeze one explicit administrative rebuild request in PostgreSQL."""

    return create_operation_with_dispatch(
        user=user,
        operation_type=SEARCH_REBUILD_OPERATION,
        source_app='community',
        source_model='PublicSearchIndex',
        source_id='public',
        input_type='community.PublicSearchIndex',
        input_id='public',
        input_version='v1',
        title='重建公共搜索索引',
        metadata={'index_scope': 'public'},
        max_attempts=5,
        queue=settings.CELERY_SEARCH_QUEUE,
        routing_key='search.index',
    )


def operation_envelope(operation) -> dict:
    return {
        'operation_id': str(operation.pk),
        'status': 'accepted',
        'events_url': f'/api/v2/operations/{operation.pk}/events/',
        'result_url': f'/api/v2/operations/{operation.pk}/',
    }


@register_operation_handler(MODERATION_OPERATION)
def moderate_content(context):
    operation = context.get_operation()
    try:
        case = ModerationCase.objects.select_related('content', 'revision').get(
            pk=operation.input_id,
            revision_id=operation.input_version,
        )
    except ModerationCase.DoesNotExist as exc:
        raise TerminalOperationError('moderation_input_not_found') from exc
    user = operation.user
    if case.content.author_id != operation.user_id and not user.is_staff:
        raise TerminalOperationError('moderation_input_forbidden')
    context.raise_if_canceled()
    redacted, findings, risk_level = inspect_and_redact(case.revision.body)
    with transaction.atomic():
        # The moderation input is the immutable ContentRevision bound to the
        # case.  A late delivery must never overwrite the risk assessment of a
        # newer revision that has since become current.
        current_revision_updated = CommunityContent.objects.filter(
            pk=case.content_id,
            current_revision_id=case.revision_id,
        ).update(risk_level=risk_level)
        ModerationCase.objects.filter(pk=case.pk).update(
            risk_level=risk_level,
            findings=findings,
        )
    context.heartbeat()
    return OperationHandlerResult(
        result_type='community.ModerationCase',
        result_id=str(case.pk),
        result={
            'content_id': str(case.content_id),
            'risk_level': risk_level,
            'finding_count': len(findings),
            'redacted': redacted != case.revision.body,
            'current_revision_updated': bool(current_revision_updated),
        },
    )


@register_operation_handler(SEARCH_REBUILD_OPERATION)
def rebuild_search_indexes(context):
    """Reload the staff principal and rebuild only through the allowlist."""

    operation = context.get_operation()
    if not can_manage_community(operation.user):
        raise TerminalOperationError('community_search_rebuild_forbidden')
    context.raise_if_canceled()
    from .tasks import rebuild_public_search_indexes
    try:
        result = rebuild_public_search_indexes.run()
    except (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError, OSError) as exc:
        from core.operations import RetryableOperationError
        raise RetryableOperationError(
            'community_search_dependency_unavailable',
            str(exc),
            retry_after_seconds=30,
        ) from exc
    except RuntimeError as exc:
        raise TerminalOperationError('community_search_not_configured', str(exc)) from exc
    context.heartbeat()
    return OperationHandlerResult(
        result_type='community.PublicSearchIndex',
        result_id='public',
        result={
            'indexes': sorted(str(key) for key in (result or {}).keys()),
            'index_count': len(result or {}),
        },
    )
