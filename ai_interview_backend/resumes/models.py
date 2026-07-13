from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Resume(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
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
    canonical_schema_version = models.CharField(max_length=20, default='1.0.0', verbose_name='JSON Resume 版本')

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
    schema_version = models.CharField(max_length=20, default='1.0.0')
    resume_json = models.JSONField(default=dict, verbose_name='标准简历 JSON')
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
