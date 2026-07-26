from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_v2 import (
    ChallengeViewSet,
    CommunityContentViewSet,
    CommunityFeedViewSet,
    GrowthEventViewSet,
    TopicViewSet,
)


router = DefaultRouter()
router.register('community/contents', CommunityContentViewSet, basename='community-content')
router.register('community/feed', CommunityFeedViewSet, basename='community-feed')
router.register('community/topics', TopicViewSet, basename='community-topic')
router.register('community/challenges', ChallengeViewSet, basename='community-challenge')
router.register('community/growth-events', GrowthEventViewSet, basename='community-growth-event')

urlpatterns = [path('', include(router.urls))]
