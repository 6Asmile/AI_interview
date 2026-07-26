from django.urls import path
from rest_framework.routers import SimpleRouter

from .views_v2 import (
    PublicResumeShareDownloadView, PublicResumeShareView, ResumeArtifactViewSet, ResumeImportV2ViewSet,
    ResumeTemplateListView, ResumeV2ViewSet,
)


router = SimpleRouter()
router.register('resumes', ResumeV2ViewSet, basename='resume-v2')
router.register('resume-imports', ResumeImportV2ViewSet, basename='resume-import-v2')
router.register('resume-artifacts', ResumeArtifactViewSet, basename='resume-artifact-v2')

urlpatterns = [
    path('resume-templates/', ResumeTemplateListView.as_view(), name='resume-template-list-v2'),
    path('resume-shares/<str:token>/', PublicResumeShareView.as_view(), name='resume-share-public-v2'),
    path('resume-shares/<str:token>/download/', PublicResumeShareDownloadView.as_view(), name='resume-share-download-v2'),
] + router.urls
