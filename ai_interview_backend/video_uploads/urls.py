from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InitUploadView,
    ChunkUploadView,
    MergeChunksView,
    UploadProgressView,
    FileUploadTaskViewSet,
    VideoTranscodeTaskViewSet,
)

router = DefaultRouter()
router.register(r'tasks', FileUploadTaskViewSet, basename='upload-task')
router.register(r'transcode-tasks', VideoTranscodeTaskViewSet, basename='transcode-task')

urlpatterns = [
    path('init/', InitUploadView.as_view(), name='init-upload'),
    path('chunk/', ChunkUploadView.as_view(), name='chunk-upload'),
    path('merge/', MergeChunksView.as_view(), name='merge-chunks'),
    path('progress/', UploadProgressView.as_view(), name='upload-progress'),
    path('', include(router.urls)),
]
