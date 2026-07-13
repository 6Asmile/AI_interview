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
    class Status(models.TextChoices):
        ACTIVE = 'active', '准备中'
        ARCHIVED = 'archived', '已归档'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_targets')
    company_name = models.CharField(max_length=200)
    position_name = models.CharField(max_length=200)
    jd_text = models.TextField(blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    location = models.CharField(max_length=120, blank=True)
    deadline = models.DateField(null=True, blank=True)
    keywords = models.JSONField(default=list, blank=True)
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
    application = models.ForeignKey(JobApplication, on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_tasks')
    interview_session = models.ForeignKey('interviews.InterviewSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_tasks')
    title = models.CharField(max_length=240)
    dimension = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO, db_index=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'priority', '-updated_at']

