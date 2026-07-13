# system/urls.py
from django.urls import path
from .views import AISettingRetrieveUpdateView, IndustryWithJobsListView, AIModelListView, AIModelGatewayHealthView  # 导入

urlpatterns = [
    path('settings/ai/', AISettingRetrieveUpdateView.as_view(), name='ai-settings'),
    path('settings/ai/health/', AIModelGatewayHealthView.as_view(), name='ai-settings-health'),
    path('jobs-by-industry/', IndustryWithJobsListView.as_view(), name='jobs-by-industry-list'),
    path('ai-models/', AIModelListView.as_view(), name='ai-model-list'), # 新增
]
