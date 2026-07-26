from rest_framework import permissions
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AsyncOperation
from .task_views import AsyncOperationSerializer


class OperationDetailView(RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AsyncOperationSerializer

    def get_queryset(self):
        return AsyncOperation.objects.filter(user=self.request.user)


class OperationEventsView(APIView):
    """Polling-safe operation event snapshot; clients may reconnect without losing state."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        operation = AsyncOperation.objects.get(pk=pk, user=request.user)
        return Response({
            'operation_id': str(operation.pk),
            'events': [{
                'event': 'operation.snapshot',
                'status': operation.status,
                'progress': operation.progress,
                'retryable': operation.retryable,
                'error_code': operation.error_code,
                'metadata': operation.metadata,
                'updated_at': operation.updated_at,
            }],
            'terminal': operation.status in {
                AsyncOperation.Status.SUCCEEDED,
                AsyncOperation.Status.FAILED,
                AsyncOperation.Status.CANCELED,
            },
            'poll_after_ms': 1000,
        })
