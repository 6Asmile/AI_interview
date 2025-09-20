# resumes/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ResumeViewSet
from .views_upload import FileUploadView
# 创建一个 router 实例
router = DefaultRouter()
# 注册 ResumeViewSet，DRF 会自动生成所有必要的 URL
# 'resumes' 是 URL 的前缀，如 /api/v1/resumes/
router.register(r'resumes', ResumeViewSet, basename='resume')

urlpatterns = [
    # 将 router 生成的 URL 包含进来
    path('', include(router.urls)),
    path('upload/resume/', FileUploadView.as_view(), name='resume-upload'),
]