# ai-interview-backend/chat/serializers.py (新建文件)

from rest_framework import serializers
from .models import Conversation, Message
from users.serializers import UserProfileSerializer  # 复用已有的用户序列化器


class MessageSerializer(serializers.ModelSerializer):
    """序列化单条消息"""
    sender = UserProfileSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'message_type', 'file_url', 'timestamp', 'is_read']


class ConversationSerializer(serializers.ModelSerializer):
    """序列化对话列表"""
    # 'participants' 默认只返回用户ID，我们需要自定义它
    participants = UserProfileSerializer(many=True, read_only=True)
    # 添加最新一条消息和未读消息数
    latest_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'participants', 'updated_at', 'latest_message', 'unread_count']

    def get_latest_message(self, obj):
        """获取该对话的最新一条消息"""
        latest = obj.messages.order_by('-timestamp').first()
        if latest:
            # 复用 MessageSerializer 来序列化
            return MessageSerializer(latest).data
        return None

    def get_unread_count(self, obj):
        """获取当前用户在该对话中的未读消息数"""
        # `self.context['request'].user` 可以获取到当前请求的用户
        user = self.context['request'].user
        if user.is_authenticated:
            # 计算由对方发送且当前用户未读的消息数量
            return obj.messages.filter(is_read=False).exclude(sender=user).count()
        return 0