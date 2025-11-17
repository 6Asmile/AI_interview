# ai-interview-backend/blog/views.py

from datetime import timedelta
from django.utils import timezone
from django.db.models import F, Q, Sum
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from django.core.cache import cache # <-- 导入 cache
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.request import Request  # 导入 Request 类型
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from interactions.models import Bookmark
from .models import Post, Category, Tag, Comment, DailyPostStats
from .serializers import (
    PostListSerializer, PostDetailSerializer, CategorySerializer,
    TagSerializer, CommentSerializer, PostCreateUpdateSerializer,
)
from .permissions import IsOwnerOrReadOnly


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """获取分类列表"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """获取标签列表"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]


class PostViewSet(viewsets.ModelViewSet):
    """
    一个集成了文章列表、详情、创建、更新、删除以及自定义功能的视图集。
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['category__slug', 'tags__slug']
    ordering_fields = ['published_at', 'view_count', 'like_count']
    ordering = ['-published_at']

    # 【已修复】移除这行导致错误的类型注解 -> action: str

    def get_queryset(self):
        """
        根据不同的 action 返回不同的查询集，实现权限控制。
        """
        queryset = Post.objects.select_related('author', 'category').prefetch_related('tags')

        # 对于非管理员用户，进行权限过滤
        if not self.request.user.is_staff:
            # 一个普通登录用户，可以看到所有已发布的文章，以及他自己的所有文章（无论状态）
            if self.request.user.is_authenticated:
                return queryset.filter(Q(status='published') | Q(author=self.request.user)).distinct()
            # 未登录用户，只能看到已发布的文章
            return queryset.filter(status='published')

        # 管理员可以看到所有文章
        return queryset

    def get_serializer_class(self):
        """
        根据不同的 action 返回不同的序列化器。
        """
        if self.action == 'list' or self.action == 'my_posts':
            return PostListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return PostCreateUpdateSerializer
        return PostDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        """
        在获取单篇文章详情时，增加浏览量。
        """
        instance = self.get_object()
        # 只有已发布的公开文章才增加浏览量
        if instance.status == 'published':
            # 使用 F 对象避免竞态条件
            instance.view_count = F('view_count') + 1
            instance.save(update_fields=['view_count'])
            instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """
        在创建文章时，自动关联作者，并根据状态设置发布时间。
        """
        if serializer.validated_data.get('status') == 'published':
            serializer.save(author=self.request.user, published_at=timezone.now())
        else:
            serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        """
        在更新文章时，处理从草稿变为发布状态的逻辑。
        """
        instance = self.get_object()
        # 仅当文章首次从非发布状态变为“published”时，才记录发布时间
        if not instance.published_at and serializer.validated_data.get('status') == 'published':
            serializer.save(published_at=timezone.now())
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        """
        重写删除方法，确保只有作者本人能删除，并返回标准状态码。
        """
        instance = self.get_object()
        if instance.author != request.user:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='my-posts')
    def my_posts(self, request: Request):
        """
        获取当前登录用户的所有文章，支持按状态筛选。
        """
        status_filter = request.query_params.get('status', None)

        # 直接从 Post 模型查询，不再依赖 get_queryset，逻辑更清晰
        queryset = Post.objects.filter(author=request.user)

        if status_filter in ['published', 'draft']:
            queryset = queryset.filter(status=status_filter)

        # 手动应用分页
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-stats')
    def my_stats(self, request: Request):
        """
        获取当前登录用户所有文章的总数据统计。
        """
        user = request.user
        post_stats = Post.objects.filter(author=user).aggregate(
            total_views=Sum('view_count'),
            total_likes=Sum('like_count'),
            total_comments=Sum('comment_count')
        )
        total_bookmarks = Bookmark.objects.filter(post__author=user).count()

        stats_data = {
            "total_views": post_stats.get('total_views') or 0,
            "total_likes": post_stats.get('total_likes') or 0,
            "total_comments": post_stats.get('total_comments') or 0,
            "total_bookmarks": total_bookmarks
        }
        return Response(stats_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='my-daily-stats')
    def my_daily_stats(self, request: Request):
        """
        获取当前登录用户文章在过去N天的每日数据趋势。
        """
        user = request.user
        try:
            days = int(request.query_params.get('days', 7))
        except (ValueError, TypeError):
            days = 7

        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)
        dates = [start_date + timedelta(days=i) for i in range(days)]

        stats = DailyPostStats.objects.filter(
            post__author=user,
            date__range=[start_date, today]
        ).values('date').annotate(
            daily_views=Sum('views'),
            daily_likes=Sum('likes')
        ).order_by('date')

        stats_map = {item['date']: item for item in stats}

        result = {
            "labels": [d.strftime('%m-%d') for d in dates],
            "views": [stats_map.get(d, {}).get('daily_views', 0) for d in dates],
            "likes": [stats_map.get(d, {}).get('daily_likes', 0) for d in dates],
        }
        return Response(result)

    @action(detail=True, methods=['get'], url_path='recommendations')
    def recommendations(self, request, pk=None):
        """
        获取一篇文章的推荐文章列表。
        """
        post = self.get_object()
        cache_key = f"recommendations:{post.id}"

        # 1. 尝试从缓存中获取
        recommended_ids = cache.get(cache_key)

        # 2. 如果缓存未命中，则同步计算一次作为后备 (可选，但能提高鲁棒性)
        if recommended_ids is None:
            from .recommendations import calculate_recommendations
            recommended_ids = calculate_recommendations(post)
            cache.set(cache_key, recommended_ids, timeout=3600)  # 存入缓存1小时

        if not recommended_ids:
            return Response([], status=status.HTTP_200_OK)

        # 3. 根据 ID 列表获取文章对象
        # 使用 in_bulk() 减少数据库查询，并保持 ID 列表的顺序
        posts_map = Post.objects.in_bulk(recommended_ids)
        recommended_posts = [posts_map[id] for id in recommended_ids if id in posts_map]

        # 4. 序列化并返回
        serializer = PostListSerializer(recommended_posts, many=True, context={'request': request})
        return Response(serializer.data)


class CommentViewSet(viewsets.ModelViewSet):
    """
    获取和创建某一篇文章下的评论。
    - 列表视图: /api/v1/posts/{post_pk}/comments/
    - 创建: POST /api/v1/posts/{post_pk}/comments/
    """
    serializer_class = CommentSerializer

    def get_permissions(self):
        # 读取评论允许任何人，但发表评论需要登录
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        # 仅返回与 URL 中 post_pk 关联的顶级评论（非回复）
        post_pk = self.kwargs.get('post_pk')
        if post_pk:
            return Comment.objects.filter(post_id=post_pk, parent__isnull=True).select_related('author').prefetch_related('replies')
        return Comment.objects.none()

    def perform_create(self, serializer):
        # 创建评论时，自动关联当前登录用户和文章
        post_pk = self.kwargs.get('post_pk')
        serializer.save(author=self.request.user, post_id=post_pk)