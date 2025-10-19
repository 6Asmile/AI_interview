# ai_interview_backend/reports/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ResumeAnalysisReportViewSet

router = DefaultRouter()
# 将 ResumeAnalysisReportViewSet 注册到 'analysis-reports' 这个 URL 基础路径上
router.register(r'analysis-reports', ResumeAnalysisReportViewSet, basename='analysis-report')

urlpatterns = [
    path('', include(router.urls)),
]