import uuid

from django.conf import settings
from django.db import models


class ConversationManager(models.Manager):
    def get_or_create_conversation(self, user1, user2, **defaults):
        qs = self.get_queryset().annotate(num_participants=models.Count('participants')).filter(
            participants=user1,
        ).filter(participants=user2).filter(num_participants=2, conversation_type=Conversation.ConversationType.USER_DM)
        if qs.exists():
            return qs.first(), False
        conv = self.create(created_by=user1, **defaults)
        conv.participants.add(user1, user2)
        ConversationParticipantState.objects.bulk_create([
            ConversationParticipantState(conversation=conv, user=user1),
            ConversationParticipantState(conversation=conv, user=user2),
        ], ignore_conflicts=True)
        return conv, True


class Conversation(models.Model):
    class ConversationType(models.TextChoices):
        USER_DM = 'user_dm', '用户私信'
        APPLICATION = 'application', '投递沟通'
        INTERVIEW_SUPPORT = 'interview_support', '面试支持'

    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    conversation_type = models.CharField(max_length=24, choices=ConversationType.choices, default=ConversationType.USER_DM, db_index=True)
    application = models.ForeignKey('careers.JobApplication', on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    interview_session = models.ForeignKey('interviews.InterviewSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='support_conversations')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_conversations')
    title = models.CharField(max_length=200, blank=True)
    objects = ConversationManager()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT = 'text', '文本'
        IMAGE = 'image', '图片'
        FILE = 'file', '文件'
        VOICE = 'voice', '语音'
        VIDEO = 'video', '视频'

    class DeliveryStatus(models.TextChoices):
        PENDING = 'pending', '待发送'
        SENT = 'sent', '已发送'
        DELIVERED = 'delivered', '已送达'
        READ = 'read', '已读'
        FAILED = 'failed', '失败'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    client_message_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=10, choices=MessageType.choices, default=MessageType.TEXT)
    file_url = models.URLField(max_length=512, blank=True, null=True, help_text='旧版兼容 URL')
    delivery_status = models.CharField(max_length=16, choices=DeliveryStatus.choices, default=DeliveryStatus.SENT, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['timestamp']
        constraints = [
            models.UniqueConstraint(fields=['conversation', 'sender', 'client_message_id'], name='uniq_chat_client_message'),
        ]


class ConversationParticipantState(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participant_states')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversation_states')
    last_read_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    muted = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation', 'user'], name='uniq_conversation_participant_state')]


class MessageAttachment(models.Model):
    class ScanStatus(models.TextChoices):
        PENDING = 'pending', '待扫描'
        CLEAN = 'clean', '安全'
        REJECTED = 'rejected', '已拒绝'

    message = models.ForeignKey(Message, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments')
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_attachments')
    file = models.FileField(upload_to='chat/attachments/%Y/%m/')
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING, db_index=True)
    scan_engine = models.CharField(max_length=80, blank=True)
    scan_detail = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class UserBlock(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_by_users')
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['blocker', 'blocked'], name='uniq_user_block')]


class MessageReport(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', '待处理'
        RESOLVED = 'resolved', '已处理'
        REJECTED = 'rejected', '已驳回'

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_reports')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reports')
    reason = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['reporter', 'message'], name='uniq_message_report')]


class ChatOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待发布'
        PUBLISHED = 'published', '已发布'
        FAILED = 'failed', '失败'

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='outbox_events')
    topic = models.CharField(max_length=160)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
