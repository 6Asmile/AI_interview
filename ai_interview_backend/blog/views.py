from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import F
from .models import Post, Category, Tag, Comment
from .serializers import (
    PostListSerializer, PostDetailSerializer, CategorySerializer,
    TagSerializer, CommentSerializer, PostCreateUpdateSerializer,
)
from .permissions import IsOwnerOrReadOnly # [核心新增] 导入自定义权限类
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

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Post.objects.all().select_related('author', 'category').prefetch_related('tags')
        return Post.objects.filter(status='published').select_related('author', 'category').prefetch_related('tags')

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