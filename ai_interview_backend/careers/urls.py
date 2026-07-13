from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CareerDashboardView, CareerFactViewSet, JobApplicationViewSet, JobTargetViewSet, LearningTaskViewSet


router = DefaultRouter()
router.register('career-facts', CareerFactViewSet, basename='career-fact')
router.register('job-targets', JobTargetViewSet, basename='job-target')
router.register('applications', JobApplicationViewSet, basename='job-application')
router.register('learning-tasks', LearningTaskViewSet, basename='learning-task')

urlpatterns = [
    path('career-dashboard/', CareerDashboardView.as_view(), name='career-dashboard'),
    path('', include(router.urls)),
]
