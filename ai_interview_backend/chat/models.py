# ai-interview-backend/chat/models.py

from django.db import models
from django.conf import settings

class ConversationManager(models.Manager):
    def get_or_create_conversation(self, user1, user2):
        # 使用 annotate 和 filter 来高效地查找包含两个用户的对话
        qs = self.get_queryset().annotate(num_participants=models.Count('participants')) \
            .filter(participants=user1).filter(participants=user2).filter(num_participants=2)
        if qs.exists():
            return qs.first(), False
        else:
            conv = self.create()
            conv.participants.add(user1, user2)
            return conv, True

class Conversation(models.Model):
    """代表两个用户之间的一次对话"""
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    objects = ConversationManager()  # 添加管理器
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class Message(models.Model):
    """代表对话中的一条消息，支持富媒体"""

    class MessageType(models.TextChoices):
        TEXT = 'text', '文本'
        IMAGE = 'image', '图片'
        FILE = 'file', '文件'
        VOICE = 'voice', '语音'
        VIDEO = 'video', '视频'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')

    # 核心字段
    content = models.TextField(blank=True, help_text="文本或表情包内容")
    message_type = models.CharField(max_length=10, choices=MessageType.choices, default=MessageType.TEXT)
    file_url = models.URLField(max_length=512, blank=True, null=True, help_text="富媒体文件的URL")

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['timestamp']