from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import F, Q
from .models import Post, Category, Tag, Comment
from .serializers import (
    PostListSerializer, PostDetailSerializer, CategorySerializer,
    TagSerializer, CommentSerializer, PostCreateUpdateSerializer,
)
from .permissions import IsOwnerOrReadOnly # [核心新增] 导入自定义权限类
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
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

    def get_queryset(self):
        # [核心修正] 重写查询逻辑
        queryset = Post.objects.select_related('author', 'category').prefetch_related('tags')

        # 对于列表视图，只显示已发布的文章
        if self.action == 'list':
            return queryset.filter(status='published')

        # 对于详情、更新、删除等操作，允许作者访问自己的非公开文章
        if self.request.user.is_authenticated:
            # 用户可以看到已发布的，或者作者是自己的
            return queryset.filter(Q(status='published') | Q(author=self.request.user))

        # 默认（未登录用户访问详情）只返回已发布的
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

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

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