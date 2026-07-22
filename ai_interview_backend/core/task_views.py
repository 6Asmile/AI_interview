from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .idempotency import run_idempotent
from .models import AsyncOperation
from .task_registry import retry_operation, sync_operations_for_user


class AsyncOperationSerializer(serializers.ModelSerializer):
    can_retry = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = AsyncOperation
        fields = [
            'id', 'operation_type', 'title', 'status', 'progress', 'error_code', 'error_message',
            'retryable', 'can_retry', 'can_cancel', 'metadata', 'started_at', 'completed_at', 'created_at', 'updated_at',
        ]

    def get_can_retry(self, obj):
        return obj.retryable and obj.status == AsyncOperation.Status.FAILED

    def get_can_cancel(self, obj):
        return obj.source_app == 'resumes' and obj.status in {AsyncOperation.Status.PENDING, AsyncOperation.Status.RUNNING}


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
            if not operation.retryable:
                return Response({'code': 'task_not_retryable', 'message': '当前任务不能重试。'}, status=status.HTTP_409_CONFLICT)
            try:
                retry_operation(operation)
            except ValueError:
                return Response({'code': 'task_not_retryable', 'message': '当前任务不能重试。'}, status=status.HTTP_409_CONFLICT)
            return Response(AsyncOperationSerializer(operation).data, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(request, f'task_retry:{pk}', execute)


class AsyncOperationCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        operation = AsyncOperation.objects.filter(pk=pk, user=request.user).first()
        if not operation:
            return Response({'code': 'task_not_found', 'message': '任务不存在。'}, status=status.HTTP_404_NOT_FOUND)
        if operation.source_app != 'resumes' or operation.status not in {AsyncOperation.Status.PENDING, AsyncOperation.Status.RUNNING}:
            return Response({'code': 'task_not_cancelable', 'message': '当前任务不能取消。'}, status=status.HTTP_409_CONFLICT)
        from resumes.models import ResumeImportJob
        ResumeImportJob.objects.filter(pk=operation.source_id, user=request.user).update(status=ResumeImportJob.Status.CANCELED)
        operation.status = AsyncOperation.Status.CANCELED
        operation.progress = 0
        operation.retryable = False
        operation.save(update_fields=['status', 'progress', 'retryable', 'updated_at'])
        return Response(AsyncOperationSerializer(operation).data)
