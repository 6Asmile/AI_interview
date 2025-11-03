from django.urls import path
from .views import LikeToggleView, BookmarkToggleView, FollowToggleView

urlpatterns = [
    path('posts/<int:pk>/like/', LikeToggleView.as_view(), name='post-like-toggle'),
    path('posts/<int:pk>/bookmark/', BookmarkToggleView.as_view(), name='post-bookmark-toggle'),
    path('users/<int:pk>/follow/', FollowToggleView.as_view(), name='user-follow-toggle'),
]