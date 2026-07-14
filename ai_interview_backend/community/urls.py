from django.urls import path

from .views import (
    CommunityFeedView,
    CommunityIndexStatusView,
    CommunityMeView,
    DiscourseConnectView,
    DiscourseWebhookView,
    PublicSearchView,
)


urlpatterns = [
    path('community/me/', CommunityMeView.as_view(), name='community-me'),
    path('community/discourse/connect/', DiscourseConnectView.as_view(), name='discourse-connect'),
    path('community/discourse/webhook/', DiscourseWebhookView.as_view(), name='discourse-webhook'),
    path('community/search/', PublicSearchView.as_view(), name='community-search'),
    path('community/feed/', CommunityFeedView.as_view(), name='community-feed'),
    path('community/index-status/', CommunityIndexStatusView.as_view(), name='community-index-status'),
]
