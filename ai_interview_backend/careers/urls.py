from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AbilitySnapshotViewSet,
    CareerDashboardView,
    CareerFactViewSet,
    CareerProfileView,
    CareerTimelineViewSet,
    EmployerCompanyViewSet,
    EmployerJobPostingViewSet,
    JobApplicationViewSet,
    JobMatchAnalysisViewSet,
    JobTargetViewSet,
    LearningPlanViewSet,
    LearningTaskViewSet,
    PublicCompanyViewSet,
    PublicJobPostingViewSet,
    WeeklyCareerReportViewSet,
)


router = DefaultRouter()
router.register('career-facts', CareerFactViewSet, basename='career-fact')
router.register('job-targets', JobTargetViewSet, basename='job-target')
router.register('applications', JobApplicationViewSet, basename='job-application')
router.register('learning-tasks', LearningTaskViewSet, basename='learning-task')
router.register('career/timeline', CareerTimelineViewSet, basename='career-timeline')
router.register('career/ability-snapshots', AbilitySnapshotViewSet, basename='ability-snapshot')
router.register('career/weekly-reports', WeeklyCareerReportViewSet, basename='weekly-career-report')
router.register('match-analyses', JobMatchAnalysisViewSet, basename='match-analysis')
router.register('learning-plans', LearningPlanViewSet, basename='learning-plan')
router.register('companies', PublicCompanyViewSet, basename='company')
router.register('jobs', PublicJobPostingViewSet, basename='job-posting')
router.register('employer/companies', EmployerCompanyViewSet, basename='employer-company')
router.register('employer/jobs', EmployerJobPostingViewSet, basename='employer-job')

urlpatterns = [
    path('career/profile/', CareerProfileView.as_view(), name='career-profile'),
    path('career-dashboard/', CareerDashboardView.as_view(), name='career-dashboard'),
    path('', include(router.urls)),
]
