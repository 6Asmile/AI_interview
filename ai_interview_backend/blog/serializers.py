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
            'comment_count', 'published_at'
        ]


# 用于文章详情的完整版序列化器
class PostDetailSerializer(PostListSerializer):
    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['content', 'word_count', 'read_time']


# 用于创建和更新文章的序列化器
# 【核心修改】创建/更新文章的序列化器
class PostCreateUpdateSerializer(serializers.ModelSerializer):
    # 【核心修改】这两个字段现在只在写入时使用，并期望接收主键 (ID)
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
        # source='category' # 默认就是 category，可以不写
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        required=False,
        # source='tags'
    )

    class Meta:
        model = Post
        # 在 fields 中包含 'category' 和 'tags' 以便写入
        fields = [
            'title', 'content', 'status', 'excerpt', 'category', 'tags',
            'cover_image', 'published_at'
        ]
        # author 等字段是只读的，在 perform_create 中自动设置
        read_only_fields = ['author', 'word_count', 'read_time']