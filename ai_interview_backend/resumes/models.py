import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Resume(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        READY = 'ready', '可投递'
        ARCHIVED = 'archived', '已归档'
        PROCESSING = 'processing', '解析中'
        PUBLISHED = 'published', '已发布'
        PARSED = 'parsed', '已解析'
        FAILED = 'failed', '解析失败'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes', verbose_name='所属用户')
    title = models.CharField(max_length=200, verbose_name='简历标题')
    file = models.FileField(upload_to='resumes/%Y/%m/', null=True, blank=True, verbose_name='上传的简历文件')
    parsed_content = models.TextField(blank=True, verbose_name='解析后的文本内容')
    content_json = models.JSONField(null=True, blank=True, verbose_name='旧版编辑器 JSON')
    template_name = models.CharField(max_length=50, blank=True, default='default', verbose_name='模板名称')
    canonical_schema_version = models.CharField(max_length=20, default='1.3.1', verbose_name='JSON Resume 版本')

    # Legacy structured fields remain readable during the compatibility window.
    full_name = models.CharField(max_length=100, blank=True, verbose_name='姓名')
    phone = models.CharField(max_length=20, blank=True, verbose_name='电话')
    email = models.EmailField(blank=True, verbose_name='邮箱')
    job_title = models.CharField(max_length=100, blank=True, verbose_name='期望职位')
    city = models.CharField(max_length=50, blank=True, verbose_name='城市')
    summary = models.TextField(blank=True, verbose_name='个人总结')

    current_version = models.ForeignKey(
        'ResumeVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='当前版本',
    )
    current_design_revision = models.ForeignKey(
        'ResumeDesignRevision',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='当前设计版本',
    )
    is_default = models.BooleanField(default=False, verbose_name='是否默认简历')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name='状态')
    optimization_suggestions = models.JSONField(null=True, blank=True, verbose_name='旧版优化建议')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    @property
    def file_url(self):
        return self.file.url if self.file else None

    class Meta:
        verbose_name = '简历'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(is_default=True),
                name='uniq_default_resume_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.title}'


class ResumeVersion(models.Model):
    class Source(models.TextChoices):
        LEGACY_MIGRATION = 'legacy_migration', '旧数据迁移'
        EDITOR = 'editor', '在线编辑'
        IMPORT = 'import', '文件导入'
        AI_SUGGESTION = 'ai_suggestion', 'AI 建议'
        JD_VARIANT = 'jd_variant', 'JD 定制'
        RESTORE = 'restore', '版本恢复'

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    schema_version = models.CharField(max_length=20, default='1.3.1')
    resume_json = models.JSONField(default=dict, verbose_name='标准简历 JSON')
    content_hash = models.CharField(max_length=64, db_index=True, blank=True)
    language = models.CharField(max_length=16, default='zh-CN')
    layout_json = models.JSONField(default=dict, blank=True, verbose_name='iFaceoff 布局 JSON')
    evidence_snapshot = models.JSONField(default=list, blank=True, verbose_name='职业事实证据快照')
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.EDITOR)
    change_summary = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resume_versions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        constraints = [
            models.UniqueConstraint(fields=['resume', 'version_number'], name='uniq_resume_version_number'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('ResumeVersion is immutable; create a new version instead.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.resume.title} v{self.version_number}'


class ResumeDraft(models.Model):
    resume = models.OneToOneField(Resume, on_delete=models.CASCADE, related_name='draft')
    base_version = models.ForeignKey(
        ResumeVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drafts',
    )
    resume_json = models.JSONField(default=dict)
    design_json = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)
    etag = models.CharField(max_length=64, db_index=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resume_drafts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class ResumeDesignRevision(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='design_revisions')
    revision_number = models.PositiveIntegerField()
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    template_key = models.CharField(max_length=48, default='ats-classic')
    template_version = models.CharField(max_length=24, default='1.0.0')
    language = models.CharField(max_length=16, default='zh-CN')
    page_size = models.CharField(max_length=12, default='A4')
    design_json = models.JSONField(default=dict)
    design_hash = models.CharField(max_length=64, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resume_design_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-revision_number']
        constraints = [
            models.UniqueConstraint(fields=['resume', 'revision_number'], name='uniq_resume_design_revision'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('ResumeDesignRevision is immutable; create a new revision instead.')
        return super().save(*args, **kwargs)


class ResumeEvidenceLink(models.Model):
    resume_version = models.ForeignKey(ResumeVersion, on_delete=models.CASCADE, related_name='evidence_links')
    json_pointer = models.CharField(max_length=500)
    career_fact = models.ForeignKey('careers.CareerFact', on_delete=models.PROTECT, related_name='resume_evidence_links')
    fact_snapshot = models.JSONField(default=dict)
    fact_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['json_pointer', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['resume_version', 'json_pointer', 'career_fact'],
                name='uniq_resume_evidence_pointer_fact',
            ),
        ]


class ResumeAsset(models.Model):
    class Kind(models.TextChoices):
        SOURCE = 'source', '原始上传'
        PARSE_INTERMEDIATE = 'parse_intermediate', '解析中间件'
        AVATAR = 'avatar', '简历头像'
        ARTIFACT = 'artifact', '导出文件'

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='assets')
    import_job = models.ForeignKey(
        'ResumeImportJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets',
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    file = models.FileField(upload_to='resume-assets/%Y/%m/')
    original_name = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ResumeArtifact(models.Model):
    class Format(models.TextChoices):
        PREVIEW = 'preview', '预览图'
        PDF = 'pdf', 'PDF'
        DOCX = 'docx', 'DOCX'
        JSON = 'json', 'JSON Resume'

    class Status(models.TextChoices):
        PENDING = 'pending', '等待生成'
        PROCESSING = 'processing', '生成中'
        READY = 'ready', '可用'
        FAILED = 'failed', '生成失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='artifacts')
    content_version = models.ForeignKey(
        ResumeVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='artifacts',
    )
    design_revision = models.ForeignKey(
        ResumeDesignRevision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='artifacts',
    )
    draft_etag = models.CharField(max_length=64, blank=True, db_index=True)
    preview_input = models.JSONField(default=dict, blank=True)
    preview_design = models.JSONField(default=dict, blank=True)
    format = models.CharField(max_length=16, choices=Format.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    asset = models.OneToOneField(
        ResumeAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artifact',
    )
    renderer_name = models.CharField(max_length=80, default='rendercv')
    renderer_version = models.CharField(max_length=40, default='2.8')
    cache_key = models.CharField(max_length=64, unique=True)
    page_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class ResumeQualityReport(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '等待评审'
        PROCESSING = 'processing', '评审中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='quality_reports')
    content_version = models.ForeignKey(ResumeVersion, on_delete=models.PROTECT, related_name='quality_reports')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    schema_version = models.CharField(max_length=20, default='1.3.1')
    config_hash = models.CharField(max_length=64, blank=True)
    score = models.PositiveSmallIntegerField(default=0)
    report_json = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class ResumeShareLink(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='share_links')
    content_version = models.ForeignKey(ResumeVersion, on_delete=models.PROTECT, related_name='share_links')
    design_revision = models.ForeignKey(ResumeDesignRevision, on_delete=models.PROTECT, related_name='share_links')
    token_hash = models.CharField(max_length=64, unique=True)
    token_hint = models.CharField(max_length=12, blank=True)
    password_hash = models.CharField(max_length=255, blank=True)
    field_policy = models.JSONField(default=dict)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    allow_download = models.BooleanField(default=False)
    download_limit = models.PositiveIntegerField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resume_share_links',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ResumeShareAccess(models.Model):
    class Action(models.TextChoices):
        VIEW = 'view', '查看'
        DOWNLOAD = 'download', '下载'
        DENIED = 'denied', '拒绝'

    share_link = models.ForeignKey(ResumeShareLink, on_delete=models.CASCADE, related_name='accesses')
    action = models.CharField(max_length=16, choices=Action.choices)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ResumeImportJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '等待解析'
        PROCESSING = 'processing', '解析中'
        REVIEW_REQUIRED = 'review_required', '等待人工确认'
        CONFIRMED = 'confirmed', '已确认'
        FAILED = 'failed', '解析失败'
        CANCELED = 'canceled', '已取消'

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='import_jobs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resume_import_jobs')
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    parser_name = models.CharField(max_length=80, blank=True)
    parser_version = models.CharField(max_length=40, blank=True)
    parser_fallback_reason = models.TextField(blank=True)
    parsed_text = models.TextField(blank=True)
    parsed_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class ResumeSuggestion(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待处理'
        ACCEPTED = 'accepted', '已采纳'
        REJECTED = 'rejected', '已拒绝'

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='suggestions')
    base_version = models.ForeignKey(ResumeVersion, on_delete=models.CASCADE, related_name='suggestions')
    patch = models.JSONField(default=list, verbose_name='JSON Patch')
    summary = models.CharField(max_length=255)
    rationale = models.TextField(blank=True)
    evidence_fact_ids = models.JSONField(default=list, blank=True)
    evidence_links = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    accepted_version = models.ForeignKey(ResumeVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resume_suggestions')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class ResumeVariant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resume_variants')
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='variants')
    source_version = models.ForeignKey(ResumeVersion, on_delete=models.PROTECT, related_name='variants')
    version = models.ForeignKey(ResumeVersion, on_delete=models.PROTECT, related_name='variant_outputs')
    job_target = models.ForeignKey('careers.JobTarget', on_delete=models.CASCADE, related_name='resume_variants')
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Education(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='educations', verbose_name='所属简历')
    school = models.CharField(max_length=100, verbose_name='学校名称')
    degree = models.CharField(max_length=50, verbose_name='学位')
    major = models.CharField(max_length=100, verbose_name='专业')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(verbose_name='结束日期')

    class Meta:
        ordering = ['-end_date']


class WorkExperience(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='work_experiences', verbose_name='所属简历')
    company = models.CharField(max_length=100, verbose_name='公司名称')
    position = models.CharField(max_length=100, verbose_name='职位')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    description = models.TextField(verbose_name='工作描述')

    class Meta:
        ordering = ['-start_date']


class ProjectExperience(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='project_experiences', verbose_name='所属简历')
    project_name = models.CharField(max_length=100, verbose_name='项目名称')
    role = models.CharField(max_length=100, verbose_name='担任角色')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    description = models.TextField(verbose_name='项目描述')

    class Meta:
        ordering = ['-start_date']


class Skill(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='skills', verbose_name='所属简历')
    skill_name = models.CharField(max_length=100, verbose_name='技能名称')
    proficiency = models.CharField(max_length=50, blank=True, verbose_name='熟练度')
