# ai_interview_backend/reports/views.py

from rest_framework import viewsets, permissions
from .models import ResumeAnalysisReport
from .serializers import ResumeAnalysisReportSerializer

class ResumeAnalysisReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    一个只读的 ViewSet，用于查看简历分析报告列表和详情。
    - GET /api/v1/analysis-reports/ -> 获取当前用户的报告列表
    - GET /api/v1/analysis-reports/{id}/ -> 获取单个报告的详情
    """
    serializer_class = ResumeAnalysisReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        重写此方法，以确保用户只能看到自己的分析报告。
        """
        return ResumeAnalysisReport.objects.filter(user=self.request.user).order_by('-created_at')