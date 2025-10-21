from django.urls import path
from .views import ResumeTemplateListView

urlpatterns = [
    path('resume-templates/', ResumeTemplateListView.as_view(), name='resume-template-list'),
]