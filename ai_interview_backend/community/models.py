import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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


class Topic(models.Model):
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    target_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CommunityContent(models.Model):
    class ContentType(models.TextChoices):
        ARTICLE = 'article', '文章'
        EXPERIENCE = 'experience', '面经'
        QUESTION = 'question', '问答'
        RESUME_CLINIC = 'resume_clinic', '简历诊所'
        PROJECT_REVIEW = 'project_review', '项目复盘'
        RESOURCE = 'resource', '学习资源'
        DISCUSSION = 'discussion', '讨论'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING = 'pending', '待审核'
        PUBLISHED = 'published', '已发布'
        REJECTED = 'rejected', '未通过'
        HIDDEN = 'hidden', '已隐藏'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_contents')
    content_type = models.CharField(max_length=24, choices=ContentType.choices, db_index=True)
    title = models.CharField(max_length=240)
    excerpt = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_anonymous = models.BooleanField(default=False)
    current_revision = models.ForeignKey(
        'ContentRevision', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    topics = models.ManyToManyField(Topic, blank=True, related_name='contents')
    target_roles = models.JSONField(default=list, blank=True)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    risk_level = models.CharField(max_length=16, default='low', db_index=True)
    legacy_source = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_id = models.CharField(max_length=120, blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['legacy_source', 'legacy_id'],
                condition=~models.Q(legacy_source=''),
                name='uniq_community_legacy_source_id',
            ),
        ]


class ContentRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='revisions')
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=240)
    body = models.TextField()
    body_hash = models.CharField(max_length=64, db_index=True)
    redacted_body = models.TextField(blank=True)
    risk_findings = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
        constraints = [
            models.UniqueConstraint(fields=['content', 'version'], name='uniq_community_content_revision'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('ContentRevision is immutable; create a new revision instead.')
        return super().save(*args, **kwargs)


class CommunityComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    body = models.TextField()
    is_anonymous = models.BooleanField(default=False)
    status = models.CharField(max_length=16, default='published', db_index=True)
    legacy_source = models.CharField(max_length=40, blank=True)
    legacy_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class Reaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_reactions')
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='reactions')
    kind = models.CharField(max_length=20, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'content', 'kind'], name='uniq_community_reaction')]


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_bookmarks')
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'content'], name='uniq_community_bookmark')]


class TopicFollow(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followed_community_topics')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'topic'], name='uniq_community_topic_follow')]


class UserFollow(models.Model):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='native_following')
    followed = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='native_followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['follower', 'followed'], name='uniq_community_user_follow')]


class ContentDailyMetric(models.Model):
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField(db_index=True)
    views = models.PositiveIntegerField(default=0)
    reactions = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['content', 'date'], name='uniq_community_content_daily_metric'),
        ]


class SharedArtifactSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shared_artifact_snapshots')
    artifact_type = models.CharField(max_length=40)
    source_object_id = models.CharField(max_length=120)
    snapshot = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64, db_index=True)
    consent_text = models.CharField(max_length=500)
    redaction_log = models.JSONField(default=list, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ContentReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_reports')
    reason = models.CharField(max_length=80)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=16, default='open', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['content', 'reporter', 'reason'], name='uniq_community_report_reason'),
        ]


class ModerationCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(CommunityContent, on_delete=models.CASCADE, related_name='moderation_cases')
    revision = models.ForeignKey(ContentRevision, on_delete=models.PROTECT, related_name='moderation_cases')
    risk_level = models.CharField(max_length=16, db_index=True)
    findings = models.JSONField(default=list)
    status = models.CharField(max_length=16, default='open', db_index=True)
    assigned_to_staff_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)


class ModerationDecision(models.Model):
    case = models.ForeignKey(ModerationCase, on_delete=models.CASCADE, related_name='decisions')
    decision = models.CharField(max_length=24)
    reason = models.TextField()
    decided_by_staff_id = models.UUIDField(null=True, blank=True)
    deterministic = models.BooleanField(default=False)
    before_snapshot = models.JSONField(default=dict)
    after_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Appeal(models.Model):
    moderation_case = models.ForeignKey(ModerationCase, on_delete=models.CASCADE, related_name='appeals')
    appellant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_appeals')
    reason = models.TextField()
    status = models.CharField(max_length=16, default='submitted', db_index=True)
    decision_reason = models.TextField(blank=True)
    decided_by_staff_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class ReputationLedger(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reputation_entries')
    event_type = models.CharField(max_length=80, db_index=True)
    points = models.IntegerField()
    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=120)
    dedup_key = models.CharField(max_length=180, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GrowthEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='growth_events')
    event_type = models.CharField(max_length=80, db_index=True)
    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=120)
    effective_date = models.DateField(db_index=True)
    points = models.PositiveIntegerField(default=1)
    dedup_key = models.CharField(max_length=180, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StreakState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='growth_streak')
    current_days = models.PositiveIntegerField(default=0)
    longest_days = models.PositiveIntegerField(default=0)
    last_effective_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class Challenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    rules = models.JSONField(default=dict)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True, db_index=True)


class ChallengeEnrollment(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='enrollments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='challenge_enrollments')
    progress = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='active', db_index=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['challenge', 'user'], name='uniq_challenge_enrollment'),
        ]
