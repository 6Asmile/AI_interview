import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class StaffAccountManager(BaseUserManager):
    def create_account(self, email, password=None, **extra):
        account = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            account.set_password(password)
        else:
            account.set_unusable_password()
        account.save(using=self._db)
        return account


class StaffRole(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=80)
    permissions = models.JSONField(default=list, blank=True)
    is_system = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class StaffAccount(AbstractBaseUser):
    class Status(models.TextChoices):
        INVITED = 'invited', '待激活'
        ACTIVE = 'active', '正常'
        SUSPENDED = 'suspended', '停用'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED, db_index=True)
    roles = models.ManyToManyField(StaffRole, related_name='accounts', blank=True)
    must_change_password = models.BooleanField(default=True)
    recovery_codes_confirmed_at = models.DateTimeField(null=True, blank=True)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StaffAccountManager()
    USERNAME_FIELD = 'email'

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def permission_set(self):
        values = set()
        for permissions in self.roles.values_list('permissions', flat=True):
            values.update(permissions or [])
        return values


class StaffSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(StaffAccount, on_delete=models.CASCADE, related_name='sessions')
    token_hash = models.CharField(max_length=64, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StaffMFADevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(StaffAccount, on_delete=models.CASCADE, related_name='mfa_devices')
    name = models.CharField(max_length=80, default='验证器')
    encrypted_secret = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StaffInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待接受'
        ACCEPTED = 'accepted', '已接受'
        REVOKED = 'revoked', '已撤销'
        EXPIRED = 'expired', '已过期'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(StaffAccount, on_delete=models.CASCADE, related_name='invitation')
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(StaffAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_invitations')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    sent_count = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StaffRecoveryCode(models.Model):
    account = models.ForeignKey(StaffAccount, on_delete=models.CASCADE, related_name='recovery_codes')
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['account', 'code_hash'], name='uniq_staff_recovery_code')]


class StaffEmailOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待发送'
        SENT = 'sent', '已发送'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invitation = models.ForeignKey(StaffInvitation, on_delete=models.CASCADE, related_name='email_events')
    to_email = models.EmailField()
    template_key = models.CharField(max_length=80, default='staff_invitation')
    encrypted_payload = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class BreakGlassGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(StaffAccount, on_delete=models.CASCADE, related_name='break_glass_grants')
    candidate_id = models.PositiveBigIntegerField(db_index=True)
    scope = models.CharField(max_length=80, default='candidate.private.read')
    operation_reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['account', 'candidate_id', 'expires_at'])]


class AdminIdempotencyRecord(models.Model):
    """Keeps staff write retries isolated from candidate identities."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(StaffAccount, on_delete=models.CASCADE, related_name='idempotency_records')
    scope = models.CharField(max_length=120, db_index=True)
    key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['account', 'scope', 'key'], name='staff_idempotency_scope_key'),
        ]
        indexes = [models.Index(fields=['account', 'scope', 'created_at'])]


class AdminAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(StaffAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_events')
    action = models.CharField(max_length=120, db_index=True)
    resource_type = models.CharField(max_length=80, db_index=True)
    resource_id = models.CharField(max_length=120, blank=True)
    operation_reason = models.CharField(max_length=500)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    before_summary = models.JSONField(default=dict, blank=True)
    after_summary = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class PlatformFeatureFlag(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False, db_index=True)
    rollout_percentage = models.PositiveSmallIntegerField(default=0)
    audience = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(StaffAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MaintenanceNotice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        SCHEDULED = 'scheduled', '已排期'
        ACTIVE = 'active', '展示中'
        ENDED = 'ended', '已结束'

    title = models.CharField(max_length=160)
    content = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(StaffAccount, on_delete=models.SET_NULL, null=True, related_name='maintenance_notices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
