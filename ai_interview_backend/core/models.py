import uuid

from django.conf import settings
from django.db import models


def default_operation_queue():
    return settings.CELERY_DEFAULT_QUEUE


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
    # ``legacy_operation_id`` preserves the request identity exposed by the
    # original idempotency implementation. New asynchronous requests bind to
    # the authoritative ``AsyncOperation`` below; this legacy value is retained
    # only for migration/audit and is never exposed as a public operation ID.
    legacy_operation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    operation = models.ForeignKey(
        'AsyncOperation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='idempotency_claims',
    )
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
    """Authoritative lifecycle for a user-visible asynchronous operation.

    Domain rows remain the source of their business result, while this record
    owns dispatch, claiming, retry/cancel and the public operation identity.
    Legacy source fields are retained so the existing task center can migrate
    incrementally without rewriting historical rows.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', '排队中'
        CLAIMED = 'claimed', '已领取'
        RUNNING = 'running', '处理中'
        RETRYING = 'retrying', '等待重试'
        REVIEW_REQUIRED = 'review_required', '待确认'
        CANCEL_REQUESTED = 'cancel_requested', '取消中'
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
    idempotency_key_hash = models.CharField(max_length=64, blank=True, db_index=True)
    input_type = models.CharField(max_length=80, blank=True)
    input_id = models.CharField(max_length=120, blank=True)
    input_version = models.CharField(max_length=120, blank=True)
    input_hash = models.CharField(max_length=64, blank=True, db_index=True)
    result_type = models.CharField(max_length=80, blank=True)
    result_id = models.CharField(max_length=120, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    lease_owner = models.CharField(max_length=160, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    fencing_token = models.PositiveBigIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    celery_task_id = models.CharField(max_length=80, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    trace_id = models.CharField(max_length=64, blank=True, db_index=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    last_event_sequence = models.PositiveBigIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'operation_type', 'idempotency_key_hash'],
                condition=~models.Q(idempotency_key_hash=''),
                name='uniq_operation_business_idempotency',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['claimed', 'running'])
                    | (
                        ~models.Q(lease_owner='')
                        & models.Q(lease_expires_at__isnull=False)
                    )
                ),
                name='operation_active_requires_lease',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['succeeded', 'failed', 'canceled'])
                    | models.Q(completed_at__isnull=False)
                ),
                name='operation_terminal_has_completed_at',
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=models.F('max_attempts')),
                name='operation_attempt_within_limit',
            ),
            models.CheckConstraint(
                condition=models.Q(progress__lte=100),
                name='operation_progress_valid',
            ),
        ]


class OperationDispatchOutbox(models.Model):
    """Durable command intent for one authoritative operation.

    The payload is deliberately limited to identifiers by the operation
    service. Workers always reload inputs and authorization context from
    PostgreSQL.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', '待投递'
        PUBLISHING = 'publishing', '投递中'
        PUBLISHED = 'published', '已投递'
        FAILED = 'failed', '待重试'
        DEAD = 'dead', '已进入死信'
        CANCELED = 'canceled', '已取消'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.ForeignKey(
        AsyncOperation,
        on_delete=models.CASCADE,
        related_name='dispatches',
    )
    task_name = models.CharField(max_length=200, default='core.tasks.execute_operation', editable=False)
    queue = models.CharField(max_length=80, default=default_operation_queue)
    routing_key = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=12)
    available_at = models.DateTimeField(db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=80, blank=True)
    last_error = models.TextField(blank=True)
    fencing_token = models.PositiveBigIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'available_at', 'created_at'], name='core_opdisp_ready_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['operation', 'fencing_token'],
                name='uniq_operation_dispatch_fence',
            ),
        ]

    def save(self, *args, **kwargs):
        # Dispatch rows are data, never executable instructions supplied by an
        # API caller. Keep the task fixed and carry only the authoritative ID.
        self.task_name = 'core.tasks.execute_operation'
        self.payload = {'operation_id': str(self.operation_id)}
        return super().save(*args, **kwargs)


class OperationEvent(models.Model):
    """Append-only durable progress/event stream for an operation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.ForeignKey(AsyncOperation, on_delete=models.CASCADE, related_name='events')
    sequence = models.PositiveBigIntegerField()
    event_type = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=24, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(fields=['operation', 'sequence'], name='uniq_operation_event_sequence'),
        ]
        indexes = [
            models.Index(fields=['operation', 'created_at'], name='core_opevent_time_idx'),
        ]


class IntegrationOutbox(models.Model):
    """Durable cross-module event waiting to be confirmed by RabbitMQ."""

    class Status(models.TextChoices):
        PENDING = 'pending', '待投递'
        PUBLISHING = 'publishing', '投递中'
        PUBLISHED = 'published', '已投递'
        FAILED = 'failed', '待重试'
        DEAD = 'dead', '已进入死信'

    class PrivacyClass(models.TextChoices):
        PUBLIC = 'public', '公开'
        INTERNAL = 'internal', '内部'
        SENSITIVE_REFERENCE = 'sensitive_reference', '敏感引用'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=120, db_index=True)
    event_version = models.PositiveSmallIntegerField(default=1)
    producer = models.CharField(max_length=64, db_index=True)
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.CharField(max_length=120, db_index=True)
    tenant_id = models.CharField(max_length=120, blank=True, db_index=True)
    actor_id = models.CharField(max_length=120, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)
    trace_id = models.CharField(max_length=64, blank=True, db_index=True)
    privacy_class = models.CharField(
        max_length=24,
        choices=PrivacyClass.choices,
        default=PrivacyClass.INTERNAL,
    )
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'available_at', 'created_at']),
            models.Index(fields=['producer', 'event_type', 'created_at']),
        ]


class ConsumerInbox(models.Model):
    """Idempotency fence for an individual integration-event consumer."""

    class Status(models.TextChoices):
        PROCESSING = 'processing', '处理中'
        PROCESSED = 'processed', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consumer_name = models.CharField(max_length=120)
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=120, db_index=True)
    event_version = models.PositiveSmallIntegerField(default=1)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROCESSING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=1)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_owner = models.CharField(max_length=160, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fencing_token = models.PositiveBigIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['consumer_name', 'event_id'],
                name='uniq_consumer_inbox_event',
            ),
        ]
        indexes = [
            models.Index(fields=['consumer_name', 'status', 'created_at']),
        ]


class RuntimePolicy(models.Model):
    """Versioned operational policy edited through the independent staff UI."""

    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True, db_index=True)
    updated_by_staff_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
