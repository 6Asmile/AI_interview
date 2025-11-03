from rest_framework import serializers

from interactions.models import Like, Bookmark, Follow
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
    # 【核心新增】添加三个 SerializerMethodField 来动态计算状态
    is_liked = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    is_author_followed = serializers.SerializerMethodField()

    class Meta(PostListSerializer.Meta):
        # 【核心新增】将新字段添加到 fields 列表
        fields = PostListSerializer.Meta.fields + [
            'content', 'word_count', 'read_time',
            'is_liked', 'is_bookmarked', 'is_author_followed'
        ]

    def get_is_liked(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return Like.objects.filter(post=obj, user=user).exists()
        return False

    def get_is_bookmarked(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return Bookmark.objects.filter(post=obj, user=user).exists()
        return False

    def get_is_author_followed(self, obj):
        user = self.context['request'].user
        if user.is_authenticated and user != obj.author:
            return Follow.objects.filter(follower=user, followed=obj.author).exists()
        return False

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