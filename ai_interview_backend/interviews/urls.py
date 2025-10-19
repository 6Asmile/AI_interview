# interviews/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InterviewSessionViewSet, PolishDescriptionView, ResumeAnalysisView # 导入新视图
router = DefaultRouter()
# 注册 ViewSet，基础 URL 为 'interviews'
router.register(r'interviews', InterviewSessionViewSet, basename='interview')

urlpatterns = [
    path('', include(router.urls)),
# 【核心新增】为 AI 润色功能添加路由
    path('polish-description/', PolishDescriptionView.as_view(), name='polish-description'),
    # 【核心新增】为简历分析功能添加路由
    path('analyze-resume/', ResumeAnalysisView.as_view(), name='analyze-resume'),
]