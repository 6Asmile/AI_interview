import uuid

from django.conf import settings
from django.db import models


class CareerFact(models.Model):
    class FactType(models.TextChoices):
        SUMMARY = 'summary', '个人总结'
        EDUCATION = 'education', '教育经历'
        WORK = 'work', '工作经历'
        PROJECT = 'project', '项目经历'
        SKILL = 'skill', '技能'
        CERTIFICATION = 'certification', '证书'
        ACHIEVEMENT = 'achievement', '成果'
        OPEN_SOURCE = 'open_source', '开源经历'

    class SourceType(models.TextChoices):
        MANUAL = 'manual', '人工录入'
        RESUME_IMPORT = 'resume_import', '简历导入'
        GITHUB = 'github', 'GitHub'
        INTERVIEW = 'interview', '面试复盘'

    class VerificationStatus(models.TextChoices):
        DRAFT = 'draft', '待确认'
        CONFIRMED = 'confirmed', '已确认'
        REJECTED = 'rejected', '已拒绝'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='career_facts')
    fact_type = models.CharField(max_length=24, choices=FactType.choices, db_index=True)
    title = models.CharField(max_length=200)
    organization = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    source_type = models.CharField(max_length=24, choices=SourceType.choices, default=SourceType.MANUAL)
    source_url = models.URLField(max_length=500, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.DRAFT,
        db_index=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['fact_type', '-updated_at']
        indexes = [models.Index(fields=['user', 'fact_type', 'verification_status'])]

    def __str__(self):
        return self.title


class JobTarget(models.Model):
    class SourceType(models.TextChoices):
        MANUAL = 'manual', '用户录入'
        COMPANY = 'company', '认证企业岗位'
        AUTHORIZED_API = 'authorized_api', '授权数据源'

    class Status(models.TextChoices):
        ACTIVE = 'active', '准备中'
        ARCHIVED = 'archived', '已归档'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_targets')
    job_posting = models.ForeignKey(
        'JobPosting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saved_targets',
    )
    job_posting_revision = models.ForeignKey(
        'JobPostingRevision',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saved_targets',
    )
    source_type = models.CharField(max_length=24, choices=SourceType.choices, default=SourceType.MANUAL, db_index=True)
    company_name = models.CharField(max_length=200)
    position_name = models.CharField(max_length=200)
    jd_text = models.TextField(blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    location = models.CharField(max_length=120, blank=True)
    deadline = models.DateField(null=True, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    jd_snapshot_hash = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.company_name} - {self.position_name}'


class JobApplication(models.Model):
    class Status(models.TextChoices):
        SAVED = 'saved', '待投递'
        APPLIED = 'applied', '已投递'
        SCREENING = 'screening', '筛选中'
        INTERVIEW = 'interview', '面试中'
        OFFER = 'offer', '已获 Offer'
        ACCEPTED = 'accepted', '已接受'
        REJECTED = 'rejected', '未通过'
        WITHDRAWN = 'withdrawn', '已撤回'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_applications')
    job_target = models.ForeignKey(JobTarget, on_delete=models.CASCADE, related_name='applications')
    resume_version = models.ForeignKey('resumes.ResumeVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    cover_letter = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SAVED, db_index=True)
    source = models.CharField(max_length=120, blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user', 'status', 'next_action_at'])]

    def __str__(self):
        return f'{self.job_target} ({self.get_status_display()})'


class ApplicationEvent(models.Model):
    application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=48)
    stage = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']


class LearningTask(models.Model):
    class Status(models.TextChoices):
        TODO = 'todo', '待完成'
        DOING = 'doing', '进行中'
        DONE = 'done', '已完成'

    class Priority(models.TextChoices):
        HIGH = 'high', '高'
        MEDIUM = 'medium', '中'
        LOW = 'low', '低'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='career_learning_tasks')
    plan = models.ForeignKey('LearningPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    application = models.ForeignKey(JobApplication, on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_tasks')
    interview_session = models.ForeignKey('interviews.InterviewSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_tasks')
    title = models.CharField(max_length=240)
    dimension = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO, db_index=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    source_type = models.CharField(max_length=48, blank=True)
    source_id = models.CharField(max_length=120, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'priority', '-updated_at']


class CareerProfile(models.Model):
    class WorkMode(models.TextChoices):
        ONSITE = 'onsite', '现场'
        HYBRID = 'hybrid', '混合'
        REMOTE = 'remote', '远程'
        FLEXIBLE = 'flexible', '不限'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='career_profile')
    target_roles = models.JSONField(default=list, blank=True)
    target_industries = models.JSONField(default=list, blank=True)
    preferred_locations = models.JSONField(default=list, blank=True)
    work_mode = models.CharField(max_length=16, choices=WorkMode.choices, default=WorkMode.FLEXIBLE)
    seniority = models.CharField(max_length=80, blank=True)
    salary_expectation = models.JSONField(default=dict, blank=True)
    goals = models.JSONField(default=list, blank=True)
    profile_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SkillTaxonomy(models.Model):
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=80, blank=True, db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']


class SkillEvidence(models.Model):
    class SourceType(models.TextChoices):
        CAREER_FACT = 'career_fact', '职业事实'
        RESUME_VERSION = 'resume_version', '简历版本'
        INTERVIEW_ANSWER = 'interview_answer', '面试回答'
        PROJECT = 'project', '项目'
        MANUAL = 'manual', '人工'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_evidence')
    skill = models.ForeignKey(SkillTaxonomy, on_delete=models.PROTECT, related_name='evidence')
    source_type = models.CharField(max_length=32, choices=SourceType.choices, db_index=True)
    source_id = models.CharField(max_length=120)
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    proficiency = models.PositiveSmallIntegerField(default=0)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    verified = models.BooleanField(default=False, db_index=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'skill', 'source_type', 'source_id'],
                name='uniq_skill_evidence_source',
            ),
            models.CheckConstraint(
                condition=models.Q(proficiency__gte=0, proficiency__lte=100),
                name='skill_evidence_proficiency_range',
            ),
        ]


class AbilitySnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ability_snapshots')
    trigger = models.CharField(max_length=80, db_index=True)
    dimensions = models.JSONField(default=dict)
    source_refs = models.JSONField(default=list, blank=True)
    config_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class Company(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待认证'
        VERIFIED = 'verified', '已认证'
        REJECTED = 'rejected', '未通过'
        SUSPENDED = 'suspended', '已停用'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    website = models.URLField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=120, blank=True, db_index=True)
    size = models.CharField(max_length=80, blank=True)
    location = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_companies')
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class CompanyVerification(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        SUBMITTED = 'submitted', '已提交'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '未通过'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='verifications')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    evidence = models.JSONField(default=list, blank=True)
    operation_reason = models.CharField(max_length=500, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    reviewed_by_staff_id = models.UUIDField(null=True, blank=True)
    review_reason = models.CharField(max_length=500, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CompanyMember(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', '所有者'
        RECRUITER = 'recruiter', '招聘成员'
        VIEWER = 'viewer', '只读成员'

    class Status(models.TextChoices):
        ACTIVE = 'active', '正常'
        INVITED = 'invited', '待接受'
        SUSPENDED = 'suspended', '停用'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company_memberships')
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.RECRUITER)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'user'], name='uniq_company_member'),
        ]


class JobPosting(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING = 'pending', '待审核'
        PUBLISHED = 'published', '已发布'
        REJECTED = 'rejected', '未通过'
        CLOSED = 'closed', '已关闭'

    class WorkMode(models.TextChoices):
        ONSITE = 'onsite', '现场'
        HYBRID = 'hybrid', '混合'
        REMOTE = 'remote', '远程'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='job_postings')
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=160, blank=True)
    work_mode = models.CharField(max_length=16, choices=WorkMode.choices, default=WorkMode.ONSITE)
    employment_type = models.CharField(max_length=40, default='full_time')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    current_revision = models.ForeignKey(
        'JobPostingRevision',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_job_postings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [models.Index(fields=['status', 'published_at'])]


class JobPostingRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='revisions')
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    jd_text = models.TextField()
    requirements = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    salary = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    approved_by_staff_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
        constraints = [
            models.UniqueConstraint(fields=['posting', 'version'], name='uniq_job_posting_revision'),
        ]


class JobMatchAnalysis(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', '排队中'
        RUNNING = 'running', '处理中'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_match_analyses')
    job_target = models.ForeignKey(JobTarget, on_delete=models.CASCADE, related_name='match_analyses')
    resume_version = models.ForeignKey('resumes.ResumeVersion', on_delete=models.PROTECT, related_name='job_match_analyses')
    job_posting_revision = models.ForeignKey(JobPostingRevision, on_delete=models.SET_NULL, null=True, blank=True, related_name='match_analyses')
    operation = models.OneToOneField('core.AsyncOperation', on_delete=models.SET_NULL, null=True, blank=True, related_name='job_match_analysis')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    jd_snapshot = models.TextField()
    jd_snapshot_hash = models.CharField(max_length=64, db_index=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    dimensions = models.JSONField(default=dict, blank=True)
    matched_skills = models.JSONField(default=list, blank=True)
    gaps = models.JSONField(default=list, blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    config_snapshot = models.JSONField(default=dict, blank=True)
    config_hash = models.CharField(max_length=64, blank=True)
    degraded = models.BooleanField(default=False)
    degradation_reason = models.CharField(max_length=160, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class LearningPlan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', '进行中'
        COMPLETED = 'completed', '已完成'
        ARCHIVED = 'archived', '已归档'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_plans')
    job_target = models.ForeignKey(JobTarget, on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_plans')
    match_analysis = models.ForeignKey(JobMatchAnalysis, on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_plans')
    interview_session = models.ForeignKey('interviews.InterviewSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='career_learning_plans')
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    source_type = models.CharField(max_length=48)
    source_id = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    config_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CareerTimelineEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='career_timeline_events')
    event_type = models.CharField(max_length=80, db_index=True)
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True)
    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)
    dedup_key = models.CharField(max_length=160)
    occurred_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'dedup_key'], name='uniq_career_timeline_dedup'),
        ]


class WeeklyCareerReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='weekly_career_reports')
    period_start = models.DateField()
    period_end = models.DateField()
    metrics = models.JSONField(default=dict)
    insights = models.JSONField(default=list, blank=True)
    next_actions = models.JSONField(default=list, blank=True)
    config_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start']
        constraints = [
            models.UniqueConstraint(fields=['user', 'period_start'], name='uniq_weekly_career_report'),
        ]
