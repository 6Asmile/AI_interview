# interviews/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EvaluationDatasetViewSet,
    EvaluationRunViewSet,
    InterviewCalibrationCaseViewSet,
    InterviewRubricViewSet,
    InterviewSessionViewSet,
    InterviewTemplateViewSet,
    PolishDescriptionView,
    ResumeAnalysisView,
)
router = DefaultRouter()
# 注册 ViewSet，基础 URL 为 'interviews'
router.register(r'interviews', InterviewSessionViewSet, basename='interview')
router.register(r'interview-templates', InterviewTemplateViewSet, basename='interview-template')
router.register(r'interview-rubrics', InterviewRubricViewSet, basename='interview-rubric')
router.register(r'interview-calibration-cases', InterviewCalibrationCaseViewSet, basename='interview-calibration-case')
router.register(r'evaluation-datasets', EvaluationDatasetViewSet, basename='evaluation-dataset')
router.register(r'evaluation-runs', EvaluationRunViewSet, basename='evaluation-run')

urlpatterns = [
    path('', include(router.urls)),
# 【核心新增】为 AI 润色功能添加路由
    path('polish-description/', PolishDescriptionView.as_view(), name='polish-description'),
    # 【核心新增】为简历分析功能添加路由
    path('analyze-resume/', ResumeAnalysisView.as_view(), name='analyze-resume'),
]
