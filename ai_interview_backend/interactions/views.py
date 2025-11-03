from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Like, Bookmark, Follow
from blog.models import Post
from users.models import User
from .serializers import FollowSerializer


class LikeToggleView(generics.GenericAPIView):
    """点赞或取消点赞一篇文章。"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = Post.objects.all()

    def post(self, request, *args, **kwargs):
        post = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, post=post)

        if not created:  # 如果已存在，则删除（取消点赞）
            like.delete()
            return Response({"status": "unliked"}, status=status.HTTP_200_OK)

        return Response({"status": "liked"}, status=status.HTTP_201_CREATED)


class BookmarkToggleView(generics.GenericAPIView):
    """收藏或取消收藏一篇文章。"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = Post.objects.all()

    def post(self, request, *args, **kwargs):
        post = self.get_object()
        bookmark, created = Bookmark.objects.get_or_create(user=request.user, post=post)

        if not created:
            bookmark.delete()
            return Response({"status": "unbookmarked"}, status=status.HTTP_200_OK)

        return Response({"status": "bookmarked"}, status=status.HTTP_201_CREATED)


class FollowToggleView(generics.GenericAPIView):
    """关注或取消关注一个用户。"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.all()

    def post(self, request, *args, **kwargs):
        followed_user = self.get_object()
        if followed_user == request.user:
            return Response({"error": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        follow, created = Follow.objects.get_or_create(follower=request.user, followed=followed_user)

        if not created:
            follow.delete()
            return Response({"status": "unfollowed"}, status=status.HTTP_200_OK)

        return Response({"status": "followed"}, status=status.HTTP_201_CREATED)