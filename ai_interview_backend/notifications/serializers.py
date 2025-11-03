from rest_framework import serializers
from .models import Notification

# 【核心修复】导入所有需要的模型和序列化器
from users.models import User
from blog.models import Post, Comment
from users.serializers import UserProfileSerializer
from blog.serializers import PostListSerializer, CommentSerializer


class GenericRelatedField(serializers.Field):
    """
    一个自定义字段，用于序列化 GenericForeignKey。
    """

    def to_representation(self, value):
        if isinstance(value, User):
            # 为了避免暴露过多用户信息，我们使用 UserProfileSerializer
            return UserProfileSerializer(value, context=self.context).data
        if isinstance(value, Post):
            # 文章列表序列化器包含了足够的信息
            return PostListSerializer(value, context=self.context).data
        if isinstance(value, Comment):
            # 评论序列化器
            return CommentSerializer(value, context=self.context).data

        # 对于其他未知类型，返回其字符串表示
        if value:
            return str(value)
        return None


class NotificationSerializer(serializers.ModelSerializer):
    actor = GenericRelatedField(read_only=True)
    target = GenericRelatedField(read_only=True)
    action_object = GenericRelatedField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'actor', 'verb', 'is_read',
            'timestamp', 'target', 'action_object'
        ]
        read_only_fields = ['recipient']  # recipient 在创建时由信号处理器指定