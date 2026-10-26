from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .idempotency import bind_current_operation, run_idempotent
from .models import AsyncOperation
from .operations import OperationConflict, request_operation_cancel, request_operation_retry
from .task_registry import (
    can_retry_legacy_source,
    retry_legacy_operation_source,
    sync_operations_for_user,
)


class AsyncOperationSerializer(serializers.ModelSerializer):
    can_retry = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = AsyncOperation
        fields = [
            'id', 'operation_type', 'title', 'status', 'progress', 'error_code', 'error_message',
            'retryable', 'can_retry', 'can_cancel', 'metadata', 'input_type', 'input_id',
            'input_version', 'input_hash', 'result_type', 'result_id', 'result_json',
            'attempt_count', 'max_attempts', 'version', 'correlation_id', 'trace_id',
            'next_attempt_at', 'cancel_requested_at', 'started_at', 'completed_at',
            'created_at', 'updated_at',
        ]

    def get_can_retry(self, obj):
        return obj.status == AsyncOperation.Status.FAILED

    def get_can_cancel(self, obj):
        return obj.status not in {
            AsyncOperation.Status.SUCCEEDED,
            AsyncOperation.Status.FAILED,
            AsyncOperation.Status.CANCELED,
        }


class AsyncOperationListView(generics.ListAPIView):
    serializer_class = AsyncOperationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        sync_operations_for_user(self.request.user)
        queryset = AsyncOperation.objects.filter(user=self.request.user)
        if self.request.query_params.get('status'):
            queryset = queryset.filter(status=self.request.query_params['status'])
        if self.request.query_params.get('operation_type'):
            queryset = queryset.filter(operation_type=self.request.query_params['operation_type'])
        return queryset


class AsyncOperationDetailView(generics.RetrieveAPIView):
    serializer_class = AsyncOperationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        sync_operations_for_user(self.request.user)
        return AsyncOperation.objects.filter(user=self.request.user)


class AsyncOperationRetryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        operation = AsyncOperation.objects.filter(pk=pk, user=request.user).first()
        if not operation:
            return Response({'code': 'task_not_found', 'message': '任务不存在。'}, status=status.HTTP_404_NOT_FOUND)

        def execute():
            uses_generic_dispatch = operation.dispatches.exists()
            if not uses_generic_dispatch and not can_retry_legacy_source(operation):
                return Response({'code': 'task_not_retryable', 'message': '当前任务不能重试。'}, status=status.HTTP_409_CONFLICT)
            try:
                updated = request_operation_retry(
                    operation.pk,
                    user=request.user,
                    dispatch_retry=uses_generic_dispatch,
                )
            except OperationConflict:
                return Response({'code': 'task_not_retryable', 'message': '当前任务不能重试。'}, status=status.HTTP_409_CONFLICT)
            if not uses_generic_dispatch:
                retry_legacy_operation_source(updated)
            bind_current_operation(updated)
            return Response(AsyncOperationSerializer(updated).data, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(request, f'task_retry:{pk}', execute, required=True)


class AsyncOperationCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        operation = AsyncOperation.objects.filter(pk=pk, user=request.user).first()
        if not operation:
            return Response({'code': 'task_not_found', 'message': '任务不存在。'}, status=status.HTTP_404_NOT_FOUND)

        def execute():
            updated = request_operation_cancel(operation.pk, user=request.user)
            if operation.source_app == 'resumes' and operation.source_model == 'ResumeImportJob':
                from resumes.models import ResumeImportJob
                ResumeImportJob.objects.filter(
                    pk=operation.source_id,
                    user=request.user,
                ).update(status=ResumeImportJob.Status.CANCELED)
            bind_current_operation(updated)
            return Response(AsyncOperationSerializer(updated).data, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(request, f'task_cancel:{pk}', execute, required=True)
