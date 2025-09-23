from rest_framework_nested import routers
from .views import (
    ResumeViewSet, 
    EducationViewSet, 
    WorkExperienceViewSet, 
    ProjectExperienceViewSet, 
    SkillViewSet
)

# 1. 创建主路由
router = routers.SimpleRouter()
router.register(r'resumes', ResumeViewSet, basename='resume')

# 2. 创建嵌套路由
resumes_router = routers.NestedSimpleRouter(router, r'resumes', lookup='resume')
resumes_router.register(r'educations', EducationViewSet, basename='resume-educations')
resumes_router.register(r'work_experiences', WorkExperienceViewSet, basename='resume-work_experiences')
resumes_router.register(r'project_experiences', ProjectExperienceViewSet, basename='resume-project_experiences')
resumes_router.register(r'skills', SkillViewSet, basename='resume-skills')

# 3. 合并所有 URL
urlpatterns = router.urls + resumes_router.urls