from rest_framework import serializers
from .models import Post, Category, Tag, Comment
from users.models import User


# 为用户信息创建一个精简的序列化器，避免暴露敏感信息
class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'avatar']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']


# 递归序列化器，用于展示层级评论
class RecursiveCommentSerializer(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    replies = RecursiveCommentSerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author', 'content', 'created_at', 'parent', 'replies']


# 用于文章列表的简化版序列化器
class PostListSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'title', 'author', 'cover_image', 'excerpt',
            'category', 'tags', 'view_count', 'like_count',
            'comment_count', 'published_at',
            'status',  # 确保 status 字段存在
            'updated_at' # 【核心修复】添加 updated_at 字段
        ]


# 用于文章详情的完整版序列化器
class PostDetailSerializer(PostListSerializer):
    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['content', 'word_count', 'read_time']


# 用于创建和更新文章的序列化器
# 【核心修改】创建/更新文章的序列化器
class PostCreateUpdateSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = Post
        fields = [
            'title', 'content', 'status', 'excerpt', 'category', 'tags',
            'cover_image'
            # 移除 'published_at'，使其不能被直接写入
        ]
        # 【核心新增】将 published_at 添加到 read_only_fields
        read_only_fields = ['author', 'word_count', 'read_time', 'published_at']