import uuid

from django.conf import settings
from django.db import models


class IdempotencyRecord(models.Model):
    """Atomically claims and stores non-streaming API operations."""

    class Status(models.TextChoices):
        PENDING = 'pending', '处理中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='idempotency_records')
    scope = models.CharField(max_length=120, db_index=True)
    key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    operation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'scope', 'key'], name='uniq_user_idempotency_scope_key'),
        ]
        indexes = [models.Index(fields=['user', 'scope', 'created_at'])]


class AsyncOperation(models.Model):
    """A lightweight cross-module task registry used by the candidate task center."""

    class Status(models.TextChoices):
        PENDING = 'pending', '排队中'
        RUNNING = 'running', '处理中'
        REVIEW_REQUIRED = 'review_required', '待确认'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'
        CANCELED = 'canceled', '已取消'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='async_operations')
    operation_type = models.CharField(max_length=80, db_index=True)
    source_app = models.CharField(max_length=40)
    source_model = models.CharField(max_length=80)
    source_id = models.CharField(max_length=80)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    retryable = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'source_app', 'source_model', 'source_id'],
                name='uniq_async_operation_source',
            ),
        ]
