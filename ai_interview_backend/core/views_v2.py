from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .idempotency import bind_current_operation, run_idempotent
from .models import AsyncOperation, OperationEvent
from .operations import OperationConflict, request_operation_cancel, request_operation_retry
from .task_registry import can_retry_legacy_source, retry_legacy_operation_source
from .task_views import AsyncOperationSerializer


class OperationEventSerializer(serializers.ModelSerializer):
    occurred_at = serializers.DateTimeField(source='created_at')
    progress = serializers.SerializerMethodField()

    def get_progress(self, obj):
        value = (obj.payload or {}).get('progress')
        return value if isinstance(value, int) else None

    class Meta:
        model = OperationEvent
        fields = ['sequence', 'event_type', 'status', 'progress', 'payload', 'occurred_at']


class OperationDetailView(RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AsyncOperationSerializer

    def get_queryset(self):
        return AsyncOperation.objects.filter(user=self.request.user)


class OperationEventsView(APIView):
    """Polling-safe operation event snapshot; clients may reconnect without losing state."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        operation = get_object_or_404(AsyncOperation, pk=pk, user=request.user)
        try:
            after_sequence = max(0, int(request.query_params.get('after_sequence') or 0))
            limit = max(1, min(int(request.query_params.get('limit') or 100), 200))
        except (TypeError, ValueError):
            return Response({
                'code': 'invalid_operation_event_cursor',
                'message': 'after_sequence 和 limit 必须是整数。',
            }, status=status.HTTP_400_BAD_REQUEST)
        events = list(operation.events.filter(sequence__gt=after_sequence).order_by('sequence')[:limit])
        serialized_events = OperationEventSerializer(events, many=True).data
        if not serialized_events:
            serialized_events = [{
                'sequence': operation.last_event_sequence,
                'event_type': 'operation.snapshot',
                'status': operation.status,
                'progress': operation.progress,
                'payload': {
                    'retryable': operation.retryable,
                    'error_code': operation.error_code,
                    'result_type': operation.result_type,
                    'result_id': operation.result_id,
                },
                'occurred_at': operation.updated_at,
            }]
        next_after_sequence = events[-1].sequence if events else operation.last_event_sequence
        return Response({
            'operation_id': str(operation.pk),
            'events': serialized_events,
            'terminal': operation.status in {
                AsyncOperation.Status.SUCCEEDED,
                AsyncOperation.Status.FAILED,
                AsyncOperation.Status.CANCELED,
            },
            'next_after_sequence': next_after_sequence,
            'poll_after_ms': 1000,
        })


class OperationRetryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        operation = get_object_or_404(AsyncOperation, pk=pk, user=request.user)

        def execute():
            uses_generic_dispatch = operation.dispatches.exists()
            if not uses_generic_dispatch and not can_retry_legacy_source(operation):
                return Response({
                    'code': 'operation_not_retryable',
                    'message': '当前操作不能通过通用重试入口重试。',
                }, status=status.HTTP_409_CONFLICT)
            try:
                updated = request_operation_retry(
                    operation.pk,
                    user=request.user,
                    dispatch_retry=uses_generic_dispatch,
                )
            except OperationConflict:
                return Response({
                    'code': 'operation_not_retryable',
                    'message': '当前操作不能重试。',
                }, status=status.HTTP_409_CONFLICT)
            if not uses_generic_dispatch:
                retry_legacy_operation_source(updated)
            bind_current_operation(updated)
            return Response({
                'operation_id': str(updated.pk),
                'status': updated.status,
                'operation': AsyncOperationSerializer(updated).data,
            }, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(request, f'operation.retry:{operation.pk}', execute, required=True)


class OperationCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        operation = get_object_or_404(AsyncOperation, pk=pk, user=request.user)

        def execute():
            updated = request_operation_cancel(operation.pk, user=request.user)
            if operation.source_app == 'resumes' and operation.source_model == 'ResumeImportJob':
                from resumes.models import ResumeImportJob
                ResumeImportJob.objects.filter(
                    pk=operation.source_id,
                    user=request.user,
                ).update(status=ResumeImportJob.Status.CANCELED)
            bind_current_operation(updated)
            return Response({
                'operation_id': str(updated.pk),
                'status': updated.status,
                'operation': AsyncOperationSerializer(updated).data,
            }, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(request, f'operation.cancel:{operation.pk}', execute, required=True)
