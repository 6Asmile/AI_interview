from django.conf import settings
from django.db import models


class CommunityIdentity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_identity')
    discourse_user_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    discourse_username = models.CharField(max_length=120, blank=True)
    trust_level = models.PositiveSmallIntegerField(default=0)
    reputation = models.IntegerField(default=0)
    profile_snapshot = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CommunityTopicLink(models.Model):
    post = models.OneToOneField('blog.Post', on_delete=models.CASCADE, null=True, blank=True, related_name='community_topic')
    discourse_topic_id = models.PositiveIntegerField(unique=True)
    topic_slug = models.SlugField(max_length=240, blank=True)
    topic_url = models.URLField(max_length=500, blank=True)
    embed_url = models.URLField(max_length=500, blank=True)
    last_posted_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CommunityWebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = 'received', '已接收'
        PROCESSED = 'processed', '已处理'
        IGNORED = 'ignored', '已忽略'
        FAILED = 'failed', '失败'

    event_id = models.CharField(max_length=160, unique=True)
    event_type = models.CharField(max_length=120, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

