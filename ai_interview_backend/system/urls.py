# system/urls.py
from django.urls import path
from .views import AISettingRetrieveUpdateView, IndustryWithJobsListView  # 导入

urlpatterns = [
    path('settings/ai/', AISettingRetrieveUpdateView.as_view(), name='ai-settings'),
    path('jobs-by-industry/', IndustryWithJobsListView.as_view(), name='jobs-by-industry-list'),
]