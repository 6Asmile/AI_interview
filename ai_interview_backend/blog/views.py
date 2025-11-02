from rest_framework import viewsets, permissions, generics, status  # <-- 新增 generics
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone # 【核心新增】导入 timezone 模块
from django.db.models import F, Q
from .models import Post, Category, Tag, Comment
from .serializers import (
    PostListSerializer, PostDetailSerializer, CategorySerializer,
    TagSerializer, CommentSerializer, PostCreateUpdateSerializer,
)
from .permissions import IsOwnerOrReadOnly # [核心新增] 导入自定义权限类
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action  # 确保导入 action
from django.db.models import Sum, Count # 导入 Sum 和 Count
from interactions.models import Bookmark # 导入 Bookmark 模型

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

# [核心修改] 将 PostViewSet 升级为 ModelViewSet
class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    # [核心修正] 同时支持三种解析器
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    # [核心修正] 配置过滤器和排序
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['category__slug', 'tags__slug']  # 允许按分类slug和标签slug过滤
    ordering_fields = ['published_at', 'view_count', 'like_count']  # 允许按这些字段排序
    ordering = ['-published_at']  # 【推荐】为列表视图添加一个默认排序

    # 【核心修复】添加类型注解，告诉 IDE self.action 的存在和类型
    action: str

    def get_queryset(self):
        # 【核心修改】为 my_posts 和 my_stats action 单独处理查询集
        if self.action in ['my_posts', 'my_stats']:
            # 在这些 action 中，我们需要访问所有状态的文章
            return Post.objects.select_related('author', 'category').prefetch_related('tags')

        # --- 以下是处理默认 action (list, retrieve, etc.) 的逻辑 ---
        queryset = Post.objects.select_related('author', 'category').prefetch_related('tags')

        # 公开的列表只显示已发布的
        if self.action == 'list':
            return queryset.filter(status='published')

        # 详情页等允许作者查看自己的草稿
        if self.request.user.is_authenticated:
            return queryset.filter(Q(status='published') | Q(author=self.request.user))

        # 未登录用户只能看已发布的
        return queryset.filter(status='published')
    def get_serializer_class(self):
        if self.action == 'list':
            return PostListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return PostCreateUpdateSerializer
        return PostDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == 'published':
            instance.view_count = F('view_count') + 1
            instance.save(update_fields=['view_count'])
            instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

        # 【核心修改】重写 perform_create

    def perform_create(self, serializer):
        # 如果创建时状态就是 'published'，则记录发布时间
        if serializer.validated_data.get('status') == 'published':
            serializer.save(author=self.request.user, published_at=timezone.now())
        else:
            serializer.save(author=self.request.user)

        # 【核心修改】重写 perform_update

    def perform_update(self, serializer):
        instance = self.get_object()
        # 仅当文章是从非发布状态 -> 'published' 状态时，才记录发布时间
        # 这可以防止每次编辑已发布的文章时都更新发布时间
        if not instance.published_at and serializer.validated_data.get('status') == 'published':
            serializer.save(published_at=timezone.now())
        else:
            serializer.save()

            # 【核心新增】一个专门用于获取当前用户所有文章的 action

    @action(detail=False, methods=['get'], url_path='my-posts')
    def my_posts(self, request):
            # 获取 URL 查询参数中的 status
            status_filter = request.query_params.get('status', None)

            # 从基础查询集开始，只筛选当前用户的文章
            queryset = self.get_queryset().filter(author=request.user)

            if status_filter in ['published', 'draft']:
                queryset = queryset.filter(status=status_filter)

            # 手动应用分页
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

            # 【核心修复】重写 destroy 方法以确保权限和清晰的返回

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # 手动进行权限检查
        if instance.author != request.user:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )

        self.perform_destroy(instance)
        # 返回一个 204 No Content 状态码，这是 RESTful API 删除成功的标准实践
        return Response(status=status.HTTP_204_NO_CONTENT)

        # 【核心新增】一个专门用于获取当前用户文章统计数据的 action

    @action(detail=False, methods=['get'], url_path='my-stats')
    def my_stats(self, request):
        user = request.user

        # 聚合用户的文章数据
        # 注意：这里的统计是总数，而非“今日”。实现“今日”需要更复杂的数据模型。
        post_stats = Post.objects.filter(author=user).aggregate(
            total_views=Sum('view_count'),
            total_likes=Sum('like_count'),
            total_comments=Sum('comment_count')
        )

        # 统计用户的文章被收藏的总数
        total_bookmarks = Bookmark.objects.filter(post__author=user).count()

        # 构造返回数据
        stats_data = {
            "total_views": post_stats.get('total_views') or 0,
            "total_likes": post_stats.get('total_likes') or 0,
            "total_comments": post_stats.get('total_comments') or 0,
            "total_bookmarks": total_bookmarks
        }

        return Response(stats_data, status=status.HTTP_200_OK)

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

