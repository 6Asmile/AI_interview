# system/urls.py
from django.urls import path
from .views import AISettingRetrieveUpdateView

urlpatterns = [
    path('settings/ai/', AISettingRetrieveUpdateView.as_view(), name='ai-settings'),
]