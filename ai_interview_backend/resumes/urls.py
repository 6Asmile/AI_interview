from rest_framework_nested import routers

from .views import (
    EducationViewSet,
    ProjectExperienceViewSet,
    ResumeImportJobViewSet,
    ResumeSuggestionViewSet,
    ResumeViewSet,
    SkillViewSet,
    WorkExperienceViewSet,
)


router = routers.SimpleRouter()
router.register(r'resumes', ResumeViewSet, basename='resume')
router.register(r'resume-imports', ResumeImportJobViewSet, basename='resume-import')
router.register(r'resume-suggestions', ResumeSuggestionViewSet, basename='resume-suggestion')

resumes_router = routers.NestedSimpleRouter(router, r'resumes', lookup='resume')
resumes_router.register(r'educations', EducationViewSet, basename='resume-educations')
resumes_router.register(r'work_experiences', WorkExperienceViewSet, basename='resume-work_experiences')
resumes_router.register(r'project_experiences', ProjectExperienceViewSet, basename='resume-project_experiences')
resumes_router.register(r'skills', SkillViewSet, basename='resume-skills')

urlpatterns = router.urls + resumes_router.urls
