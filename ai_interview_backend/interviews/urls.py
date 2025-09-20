# interviews/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InterviewSessionViewSet

router = DefaultRouter()
# 注册 ViewSet，基础 URL 为 'interviews'
router.register(r'interviews', InterviewSessionViewSet, basename='interview')

urlpatterns = [
    path('', include(router.urls)),
]