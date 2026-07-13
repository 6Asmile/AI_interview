from django.urls import path

from .views import CommunityMeView, DiscourseConnectView, DiscourseWebhookView, PublicSearchView


urlpatterns = [
    path('community/me/', CommunityMeView.as_view(), name='community-me'),
    path('community/discourse/connect/', DiscourseConnectView.as_view(), name='discourse-connect'),
    path('community/discourse/webhook/', DiscourseWebhookView.as_view(), name='discourse-webhook'),
    path('community/search/', PublicSearchView.as_view(), name='community-search'),
]

