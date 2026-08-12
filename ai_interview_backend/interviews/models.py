# interviews/models.py
from django.db import models
import uuid
from users.models import User
from resumes.models import Resume


class AgentConfigProfile(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = 'platform', '平台默认'
        TEMPLATE = 'template', '模板覆盖'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.TEMPLATE, db_index=True)
    active_revision = models.ForeignKey(
        'AgentConfigRevision',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_by_staff = models.ForeignKey(
        'staff_admin.StaffAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_agent_config_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scope', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['scope'],
                condition=models.Q(scope='platform'),
                name='uniq_platform_agent_config_profile',
            ),
        ]

    def __str__(self):
        return self.name


class AgentConfigRevision(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING_REVIEW = 'pending_review', '待审核'
        APPROVED = 'approved', '已审核'
        PUBLISHED = 'published', '已发布'
        REJECTED = 'rejected', '已拒绝'
        SUPERSEDED = 'superseded', '已替代'

    class ComponentMode(models.TextChoices):
        INHERIT = 'inherit', '继承平台配置'
        REPLACE = 'replace', '完整替换'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(AgentConfigProfile, on_delete=models.CASCADE, related_name='revisions')
    base_revision = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_revisions',
    )
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    context_mode = models.CharField(max_length=16, choices=ComponentMode.choices, default=ComponentMode.REPLACE)
    context_policy = models.JSONField(default=dict, blank=True)
    knowledge_mode = models.CharField(max_length=16, choices=ComponentMode.choices, default=ComponentMode.INHERIT)
    config_hash = models.CharField(max_length=64, blank=True, db_index=True)
    validation_report = models.JSONField(default=dict, blank=True)
    evaluation_summary = models.JSONField(default=dict, blank=True)
    change_summary = models.TextField(blank=True)
    created_by_staff = models.ForeignKey(
        'staff_admin.StaffAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_agent_config_revisions',
    )
    approved_by_staff = models.ForeignKey(
        'staff_admin.StaffAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_agent_config_revisions',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['profile', '-version']
        constraints = [
            models.UniqueConstraint(fields=['profile', 'version'], name='uniq_agent_config_revision'),
        ]

    def __str__(self):
        return f'{self.profile.name} v{self.version}'


class AgentPromptTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(AgentConfigRevision, on_delete=models.CASCADE, related_name='prompts')
    task_key = models.CharField(max_length=120, db_index=True)
    system_template = models.TextField()
    user_template = models.TextField()
    variable_schema = models.JSONField(default=dict, blank=True)
    output_contract = models.JSONField(default=dict, blank=True)
    model_alias = models.ForeignKey(
        'system.ModelAlias',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agent_prompt_templates',
    )
    temperature = models.DecimalField(max_digits=3, decimal_places=2, default=0.3)
    max_output_tokens = models.PositiveIntegerField(default=800)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['revision', 'task_key']
        constraints = [
            models.UniqueConstraint(fields=['revision', 'task_key'], name='uniq_agent_prompt_task_revision'),
        ]

    def __str__(self):
        return f'{self.revision} {self.task_key}'


class AgentConfigKnowledgeBinding(models.Model):
    revision = models.ForeignKey(AgentConfigRevision, on_delete=models.CASCADE, related_name='knowledge_bindings')
    knowledge_base_revision = models.ForeignKey(
        'knowledge.KnowledgeBaseRevision',
        on_delete=models.PROTECT,
        related_name='agent_config_bindings',
    )
    retrieval_profile_revision = models.ForeignKey(
        'knowledge.RetrievalProfileRevision',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agent_config_overrides',
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['revision', 'knowledge_base_revision'],
                name='uniq_agent_config_knowledge_binding',
            ),
        ]


class AgentConfigEvaluationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待运行'
        RUNNING = 'running', '运行中'
        SUCCEEDED = 'succeeded', '成功'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(
        AgentConfigRevision,
        on_delete=models.CASCADE,
        related_name='config_evaluation_runs',
    )
    baseline_revision = models.ForeignKey(
        AgentConfigRevision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='baseline_config_evaluation_runs',
    )
    dataset = models.ForeignKey(
        'EvaluationDataset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_config_evaluation_runs',
    )
    evaluation_type = models.CharField(max_length=32, default='full', db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    metrics = models.JSONField(default=dict, blank=True)
    result_samples = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    revision_hash = models.CharField(max_length=64, db_index=True)
    created_by_staff = models.ForeignKey(
        'staff_admin.StaffAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_config_evaluation_runs',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class InterviewRubric(models.Model):
    class Visibility(models.TextChoices):
        SYSTEM = 'system', '系统内置'
        SHARED = 'shared', '共享'
        PRIVATE = 'private', '私有'

    name = models.CharField(max_length=120, verbose_name='量表名称')
    description = models.TextField(blank=True, verbose_name='量表说明')
    version = models.PositiveIntegerField(default=1, verbose_name='版本')
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PRIVATE)
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_rubrics')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试评分量表'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.name} v{self.version}'


class RubricDimension(models.Model):
    rubric = models.ForeignKey(InterviewRubric, on_delete=models.CASCADE, related_name='dimensions')
    key = models.CharField(max_length=80, verbose_name='维度标识')
    name = models.CharField(max_length=120, verbose_name='维度名称')
    description = models.TextField(blank=True, verbose_name='维度说明')
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1, verbose_name='权重')
    min_coverage = models.PositiveIntegerField(default=1, verbose_name='最低覆盖次数')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    rule_config = models.JSONField(default=dict, blank=True, verbose_name='规则评分配置')

    class Meta:
        verbose_name = '评分维度'
        verbose_name_plural = verbose_name
        ordering = ['rubric', 'order', 'id']
        unique_together = ('rubric', 'key')

    def __str__(self):
        return self.name


class RubricLevelAnchor(models.Model):
    dimension = models.ForeignKey(RubricDimension, on_delete=models.CASCADE, related_name='anchors')
    level = models.CharField(max_length=30, verbose_name='等级')
    min_score = models.PositiveIntegerField(default=0, verbose_name='最低分')
    max_score = models.PositiveIntegerField(default=100, verbose_name='最高分')
    description = models.TextField(verbose_name='等级描述')

    class Meta:
        verbose_name = '评分等级锚点'
        verbose_name_plural = verbose_name
        ordering = ['dimension', 'min_score']

    def __str__(self):
        return f'{self.dimension.name} {self.level}'


class InterviewTemplate(models.Model):
    class Visibility(models.TextChoices):
        SYSTEM = 'system', '系统内置'
        SHARED = 'shared', '共享'
        PRIVATE = 'private', '私有'

    class InterviewMode(models.TextChoices):
        RELAXED = 'relaxed', '宽松交流'
        STRICT = 'strict', '严格追问'
        FUNDAMENTALS = 'fundamentals', '基础知识'
        PROJECT_DEEP_DIVE = 'project_deep_dive', '项目深挖'
        PROJECT_WITH_FUNDAMENTALS = 'project_with_fundamentals', '项目穿插基础知识'
        SYSTEM_DESIGN = 'system_design', '系统设计'
        BEHAVIORAL = 'behavioral', '行为面试'
        STRUCTURED = 'structured', '结构化面试'

    name = models.CharField(max_length=120, verbose_name='模板名称')
    description = models.TextField(blank=True, verbose_name='模板说明')
    job_keywords = models.JSONField(default=list, blank=True, verbose_name='岗位匹配关键词')
    rubric = models.ForeignKey(InterviewRubric, on_delete=models.PROTECT, related_name='templates')
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PRIVATE)
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='是否启用')
    version = models.PositiveIntegerField(default=1, verbose_name='版本')
    require_rag = models.BooleanField(default=False, verbose_name='是否强制要求知识库依据')
    interview_mode = models.CharField(
        max_length=40,
        choices=InterviewMode.choices,
        default=InterviewMode.PROJECT_WITH_FUNDAMENTALS,
        verbose_name='面试模式',
    )
    target_duration_minutes = models.PositiveIntegerField(default=30, verbose_name='目标时长（分钟）')
    min_duration_minutes = models.PositiveIntegerField(default=20, verbose_name='最短时长（分钟）')
    hard_max_duration_minutes = models.PositiveIntegerField(default=45, verbose_name='最长时长（分钟）')
    min_turns = models.PositiveIntegerField(default=5, verbose_name='最少有效轮次')
    max_turns = models.PositiveIntegerField(default=18, verbose_name='异常保护最大轮次')
    candidate_question_minutes = models.PositiveIntegerField(default=3, verbose_name='候选人反问预留时长')
    style_profile = models.JSONField(default=dict, blank=True, verbose_name='面试风格配置')
    config = models.JSONField(default=dict, blank=True, verbose_name='模板配置')
    agent_config_profile = models.ForeignKey(
        AgentConfigProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interview_templates',
        limit_choices_to={'scope': AgentConfigProfile.Scope.TEMPLATE},
        verbose_name='Agent配置覆盖',
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试模板'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.name} v{self.version}'


class InterviewTemplateStage(models.Model):
    template = models.ForeignKey(InterviewTemplate, on_delete=models.CASCADE, related_name='stages')
    stage_key = models.CharField(max_length=32, verbose_name='阶段标识')
    name = models.CharField(max_length=80, verbose_name='阶段名称')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    question_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='题量占比')
    target_dimensions = models.JSONField(default=list, blank=True, verbose_name='目标能力维度')
    question_guidance = models.TextField(blank=True, verbose_name='出题指引')
    min_duration_minutes = models.PositiveIntegerField(default=0, verbose_name='阶段最短时长（分钟）')
    max_duration_minutes = models.PositiveIntegerField(default=0, verbose_name='阶段最长时长（分钟）')
    min_verified_dimensions = models.PositiveIntegerField(default=0, verbose_name='最低验证能力数')
    allowed_question_types = models.JSONField(default=list, blank=True, verbose_name='允许题型')
    entry_condition = models.JSONField(default=dict, blank=True, verbose_name='进入条件')
    exit_condition = models.JSONField(default=dict, blank=True, verbose_name='退出条件')
    allow_topic_return = models.BooleanField(default=True, verbose_name='允许返回上层话题')

    class Meta:
        verbose_name = '面试模板阶段'
        verbose_name_plural = verbose_name
        ordering = ['template', 'order', 'id']
        unique_together = ('template', 'stage_key')

    def __str__(self):
        return self.name


class InterviewCalibrationCase(models.Model):
    rubric = models.ForeignKey(InterviewRubric, on_delete=models.CASCADE, related_name='calibration_cases')
    title = models.CharField(max_length=160, verbose_name='校准样例标题')
    job_position = models.CharField(max_length=120, verbose_name='岗位')
    question = models.TextField(verbose_name='问题')
    answer = models.TextField(verbose_name='匿名化真实回答')
    expected_scores = models.JSONField(default=dict, blank=True, verbose_name='期望评分')
    expected_dimensions = models.JSONField(default=list, blank=True, verbose_name='期望能力标签')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='interview_calibration_cases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '面试评分校准样例'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class InterviewSession(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待开始'
        RUNNING = 'running', '进行中'
        FINISHED = 'finished', '已完成'
        CANCELED = 'canceled', '已取消'

    class InterviewStage(models.TextChoices):
        OPENING = 'opening', '开场定位'
        SELF_INTRO = 'self_intro', '自我介绍'
        PROJECT_ANCHOR = 'project_anchor', '项目定位'
        PROJECT_DEEP_DIVE = 'project_deep_dive', '项目深挖'
        FUNDAMENTALS_PROBE = 'fundamentals_probe', '基础知识验证'
        ROLE_SPECIFIC = 'role_specific', '岗位专项'
        SYSTEM_DESIGN = 'system_design', '系统设计'
        BEHAVIORAL = 'behavioral', '行为面试'
        CANDIDATE_QUESTIONS = 'candidate_questions', '候选人反问'
        CLOSING = 'closing', '自然收尾'
        RESUME_DEEP_DIVE = 'resume_deep_dive', '简历深挖'
        TECHNICAL_DEEP_DIVE = 'technical_deep_dive', '技术深挖'
        SCENARIO_CHALLENGE = 'scenario_challenge', '场景挑战'
        WRAP_UP = 'wrap_up', '收尾复盘'

    class Difficulty(models.TextChoices):
        EASY = 'easy', '简单'
        MEDIUM = 'medium', '中等'
        HARD = 'hard', '困难'

    class ExperienceMode(models.TextChoices):
        REALISTIC = 'realistic', '真实模拟'
        COACHING = 'coaching', '训练指导'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='会话 UUID')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_sessions', verbose_name='所属用户')
    resume = models.ForeignKey(Resume, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联简历')
    resume_version = models.ForeignKey(
        'resumes.ResumeVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interview_sessions',
        verbose_name='简历版本快照来源',
    )
    job_target = models.ForeignKey(
        'careers.JobTarget',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interview_sessions',
        verbose_name='求职目标',
    )
    resume_snapshot = models.JSONField(default=dict, blank=True, verbose_name='简历快照')
    jd_snapshot = models.TextField(blank=True, verbose_name='JD 快照')

    job_position = models.CharField(max_length=100, verbose_name='目标岗位')
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.MEDIUM,
                                  verbose_name='难度')
    question_count = models.IntegerField(default=5, verbose_name='问题数量')
    target_duration_minutes = models.PositiveIntegerField(default=30, verbose_name='目标时长（分钟）')
    experience_mode = models.CharField(
        max_length=20,
        choices=ExperienceMode.choices,
        default=ExperienceMode.REALISTIC,
        verbose_name='体验模式',
    )
    interview_mode = models.CharField(max_length=40, blank=True, default='', verbose_name='面试模式')
    progress_mode = models.CharField(max_length=32, default='question_count', verbose_name='进度计算模式')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='状态')
    current_stage = models.CharField(
        max_length=32,
        choices=InterviewStage.choices,
        default=InterviewStage.OPENING,
        verbose_name='当前面试阶段'
    )
    duration = models.IntegerField(null=True, blank=True, verbose_name='持续时间 (秒)')

    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    report = models.JSONField(null=True, blank=True, verbose_name='面试报告')
    template = models.ForeignKey(
        InterviewTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions',
        verbose_name='面试模板'
    )
    session_plan = models.JSONField(default=dict, blank=True, verbose_name='本场面试计划快照')
    template_snapshot = models.JSONField(default=dict, blank=True, verbose_name='模板快照')
    agent_config_snapshot = models.JSONField(default=dict, blank=True, verbose_name='Agent配置快照')
    coverage_summary = models.JSONField(default=dict, blank=True, verbose_name='能力覆盖汇总')
    memory_summary = models.JSONField(default=dict, blank=True, verbose_name='短期记忆摘要')
    covered_topics = models.JSONField(default=list, blank=True, verbose_name='已覆盖话题')
    pending_topics = models.JSONField(default=list, blank=True, verbose_name='待追问话题')
    perception_summary = models.JSONField(default=dict, blank=True, verbose_name='感知摘要')
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='最后活动时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    recording_enabled = models.BooleanField(default=False, verbose_name='是否开启录像')
    video_upload_task = models.ForeignKey(
        'video_uploads.FileUploadTask',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interview_sessions',
        verbose_name='视频上传任务'
    )



    class Meta:
        verbose_name = '面试会话'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'面试会话: {self.job_position} ({self.user.username})'


class InterviewQuestion(models.Model):
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions',
                                verbose_name='所属会话')

    question_text = models.TextField(verbose_name='问题内容')
    sequence = models.IntegerField(verbose_name='问题序号')

    # 用户回答相关字段
    answer_text = models.TextField(blank=True, verbose_name='用户回答文本')
    audio_url = models.CharField(max_length=255, blank=True, verbose_name='回答音频 URL')

    # 新增：用于存储前端发送的情绪/动作时间序列数据
    analysis_data = models.JSONField(null=True, blank=True, verbose_name='实时分析数据')
    # AI 评估相关字段
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='得分')
    ai_feedback = models.JSONField(null=True, blank=True, verbose_name='AI 反馈内容')
    rag_context = models.JSONField(default=list, blank=True, verbose_name='RAG题库上下文')
    question_plan = models.JSONField(default=dict, blank=True, verbose_name='题目生成计划')
    question_signature = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='题目语义签名')
    target_dimension = models.CharField(max_length=80, blank=True, db_index=True, verbose_name='目标能力维度')
    generation_mode = models.CharField(max_length=32, blank=True, default='legacy', verbose_name='生成模式')
    validation_status = models.CharField(max_length=32, blank=True, default='not_validated', verbose_name='校验状态')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name='回答时间')
    evaluated_at = models.DateTimeField(null=True, blank=True, verbose_name='评估时间')

    class Meta:
        verbose_name = '面试问题'
        verbose_name_plural = verbose_name
        ordering = ['session', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['session', 'sequence'], name='uniq_interview_question_sequence'),
        ]

    def __str__(self):
        return f'问题 {self.sequence}: {self.question_text[:30]}...'


class InterviewQuestionGenerationJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待生成'
        RUNNING = 'running', '生成中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='question_generation_jobs',
        verbose_name='面试会话'
    )
    answered_question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_generation_jobs',
        verbose_name='已回答问题'
    )
    generated_question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generation_jobs',
        verbose_name='生成的问题'
    )
    sequence = models.PositiveIntegerField(verbose_name='目标题号')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    request_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='请求哈希')
    engine_name = models.CharField(max_length=40, blank=True, verbose_name='Agent引擎')
    partial_text = models.TextField(blank=True, verbose_name='部分生成文本')
    final_text = models.TextField(blank=True, verbose_name='最终生成文本')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试下一题生成任务'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['session', 'sequence'], name='uniq_interview_generation_job_sequence')
        ]
        indexes = [
            models.Index(fields=['session', 'status', 'updated_at']),
            models.Index(fields=['request_hash']),
        ]

    def __str__(self):
        return f'{self.session_id} Q{self.sequence} {self.status}'


class InterviewAgentRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待运行'
        RUNNING = 'running', '运行中'
        WAITING_GENERATION = 'waiting_generation', '等待生成'
        COMPLETED = 'completed', '已完成'
        DEGRADED = 'degraded', '降级完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='agent_runs',
        verbose_name='面试会话',
    )
    trigger_question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_runs',
        verbose_name='触发问题',
    )
    event = models.CharField(max_length=50, db_index=True, verbose_name='事件')
    request_hash = models.CharField(max_length=64, db_index=True, verbose_name='幂等请求哈希')
    engine_name = models.CharField(max_length=40, default='composite_v2', verbose_name='Agent引擎')
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    state_schema_version = models.PositiveSmallIntegerField(default=2)
    current_node = models.CharField(max_length=80, blank=True, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    state_snapshot = models.JSONField(default=dict, blank=True)
    fallback_reason = models.CharField(max_length=200, blank=True)
    error_message = models.TextField(blank=True)
    model_config_snapshot = models.JSONField(default=dict, blank=True)
    prompt_version = models.CharField(max_length=80, blank=True, db_index=True)
    agent_config_revision_id = models.UUIDField(null=True, blank=True, db_index=True)
    agent_config_hash = models.CharField(max_length=64, blank=True, db_index=True)
    prompt_hashes = models.JSONField(default=dict, blank=True)
    context_envelope_hash = models.CharField(max_length=64, blank=True, db_index=True)
    context_token_usage = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试Agent运行'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'event', 'request_hash'],
                name='uniq_interview_agent_run_request',
            )
        ]
        indexes = [
            models.Index(fields=['session', 'status', 'updated_at']),
            models.Index(fields=['session', 'event', 'created_at']),
        ]

    def __str__(self):
        return f'{self.session_id} {self.event} {self.status}'


class InterviewAgentExecution(models.Model):
    """Business-level pointer to a LangGraph run.

    Checkpoints and node writes live in the dedicated ``ifaceoff_agent``
    database. Django stores only the identifiers and lifecycle metadata that
    the product needs for authorization, recovery and audit navigation.
    """

    class Status(models.TextChoices):
        ACCEPTED = 'accepted', '已接受'
        ANSWER_PERSISTED = 'answer_persisted', '回答已持久化'
        EVALUATING = 'evaluating', '评估中'
        EVALUATED = 'evaluated', '评估完成'
        GENERATING = 'generating', '生成下一题'
        FAILED_RETRYABLE = 'failed_retryable', '可重试失败'
        FAILED_TERMINAL = 'failed_terminal', '终止失败'
        PENDING = 'pending', '待执行'
        RUNNING = 'running', '执行中'
        WAITING = 'waiting', '等待生成或恢复'
        COMPLETED = 'completed', '已完成'
        DEGRADED = 'degraded', '降级完成'
        FAILED = 'failed', '执行失败'
        CANCELED = 'canceled', '已取消'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.OneToOneField(
        'core.AsyncOperation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interview_agent_execution',
        verbose_name='平台异步操作',
    )
    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='agent_executions',
        verbose_name='面试会话',
    )
    trigger_question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_executions',
        verbose_name='触发问题',
    )
    legacy_run = models.OneToOneField(
        InterviewAgentRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='execution',
        verbose_name='兼容运行记录',
    )
    thread_id = models.UUIDField(db_index=True, verbose_name='LangGraph Thread ID')
    run_id = models.UUIDField(unique=True, verbose_name='LangGraph Run ID')
    event = models.CharField(max_length=50, db_index=True, verbose_name='业务事件')
    idempotency_key = models.CharField(max_length=128, verbose_name='幂等键')
    request_hash = models.CharField(max_length=64, db_index=True, verbose_name='请求哈希')
    checkpoint_namespace = models.CharField(max_length=180, blank=True, verbose_name='Checkpoint命名空间')
    engine_version = models.CharField(max_length=40, default='composite_v4', db_index=True)
    state_schema_version = models.PositiveSmallIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    version = models.PositiveIntegerField(default=0, verbose_name='状态版本')
    fencing_token = models.PositiveBigIntegerField(default=0, verbose_name='执行栅栏令牌')
    lease_owner = models.CharField(max_length=128, blank=True, db_index=True, verbose_name='租约持有者')
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='租约过期时间')
    heartbeat_at = models.DateTimeField(null=True, blank=True, verbose_name='最近心跳时间')
    retry_count = models.PositiveSmallIntegerField(default=0, verbose_name='重试次数')
    last_durable_sequence = models.PositiveIntegerField(default=0, verbose_name='最后持久化事件序号')
    state_metadata = models.JSONField(default=dict, blank=True, verbose_name='持久化状态摘要')
    result_question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='result_agent_executions',
        verbose_name='生成结果问题',
    )
    fallback_reason = models.CharField(max_length=200, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    last_event_id = models.CharField(max_length=160, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试Agent执行映射'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'event', 'idempotency_key'],
                name='uniq_agent_execution_idempotency',
            ),
        ]
        indexes = [
            models.Index(fields=['session', 'status', 'updated_at']),
            models.Index(fields=['thread_id', 'created_at']),
            models.Index(fields=['status', 'lease_expires_at'], name='interviews_status_lease_idx'),
        ]

    def __str__(self):
        return f'{self.session_id} {self.event} {self.status}'


class InterviewAgentDispatch(models.Model):
    """Transactional outbox entry for an Agent execution."""

    class Status(models.TextChoices):
        PENDING = 'pending', '待投递'
        PUBLISHED = 'published', '已投递'
        FAILED = 'failed', '投递失败'
        CANCELED = 'canceled', '已取消'

    execution = models.OneToOneField(
        InterviewAgentExecution,
        on_delete=models.CASCADE,
        related_name='dispatch',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    celery_task_id = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['status', 'next_attempt_at', 'created_at'])]


class InterviewReferenceAnswer(models.Model):
    """Durable AI reference answer; Redis is only an acceleration layer."""

    class Status(models.TextChoices):
        PENDING = 'pending', '生成中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(InterviewQuestion, on_delete=models.CASCADE, related_name='reference_answers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_reference_answers')
    prompt_version = models.CharField(max_length=80)
    model_alias = models.CharField(max_length=120)
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_code = models.CharField(max_length=120, blank=True)
    source_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'user', 'prompt_version', 'model_alias'],
                name='uniq_interview_reference_answer_snapshot',
            )
        ]
        indexes = [models.Index(fields=['user', 'status', 'updated_at'])]


class InterviewAgentNodeRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running', '运行中'
        SUCCEEDED = 'succeeded', '成功'
        SKIPPED = 'skipped', '跳过'
        DEGRADED = 'degraded', '降级'
        FAILED = 'failed', '失败'

    run = models.ForeignKey(
        InterviewAgentRun,
        on_delete=models.CASCADE,
        related_name='node_runs',
        verbose_name='Agent运行',
    )
    node_name = models.CharField(max_length=80, db_index=True)
    subagent_name = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING, db_index=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    input_hash = models.CharField(max_length=64, blank=True)
    output_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    fallback_reason = models.CharField(max_length=200, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '面试Agent节点运行'
        verbose_name_plural = verbose_name
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'node_name', 'attempt'],
                name='uniq_interview_agent_node_attempt',
            )
        ]
        indexes = [
            models.Index(fields=['run', 'status', 'created_at']),
            models.Index(fields=['subagent_name', 'status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.run_id} {self.node_name}#{self.attempt} {self.status}'


class InterviewAgentTrace(models.Model):
    agent_run = models.ForeignKey(
        InterviewAgentRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='traces',
        verbose_name='Agent运行',
    )
    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='agent_traces',
        verbose_name='面试会话'
    )
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_traces',
        verbose_name='关联问题'
    )
    event = models.CharField(max_length=50, default='submit_answer', verbose_name='事件')
    stage = models.CharField(max_length=32, blank=True, verbose_name='阶段')
    node_outputs = models.JSONField(default=dict, blank=True, verbose_name='节点输出')
    answer_evaluation = models.JSONField(default=dict, blank=True, verbose_name='回答评估摘要')
    rag_context = models.JSONField(default=list, blank=True, verbose_name='RAG来源')
    question_plan = models.JSONField(default=dict, blank=True, verbose_name='题目计划')
    generated_question = models.TextField(blank=True, verbose_name='最终问题')
    fallback_reason = models.CharField(max_length=200, blank=True, verbose_name='降级原因')
    input_hash = models.CharField(max_length=64, blank=True, verbose_name='输入哈希')
    output_summary = models.JSONField(default=dict, blank=True, verbose_name='输出摘要')
    validation_errors = models.JSONField(default=list, blank=True, verbose_name='校验错误')
    model_config_snapshot = models.JSONField(default=dict, blank=True, verbose_name='模型配置快照')
    subagent_name = models.CharField(max_length=80, blank=True, db_index=True, verbose_name='主导SubAgent')
    loop_iteration = models.PositiveSmallIntegerField(default=1, verbose_name='Agent Loop轮次')
    context_budget = models.JSONField(default=dict, blank=True, verbose_name='上下文预算')
    prompt_version = models.CharField(max_length=80, blank=True, db_index=True, verbose_name='Prompt版本')
    compressed_context_summary = models.JSONField(default=dict, blank=True, verbose_name='压缩上下文摘要')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '面试Agent轨迹'
        verbose_name_plural = verbose_name
        ordering = ['created_at']

    def __str__(self):
        return f'{self.session_id} {self.event} {self.created_at:%Y-%m-%d %H:%M:%S}'


class InterviewAgentToolCall(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'success', '成功'
        DEGRADED = 'degraded', '降级'
        FAILED = 'failed', '失败'

    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='agent_tool_calls',
        verbose_name='面试会话'
    )
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_tool_calls',
        verbose_name='关联问题'
    )
    trace = models.ForeignKey(
        InterviewAgentTrace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tool_calls',
        verbose_name='关联轨迹'
    )
    event = models.CharField(max_length=50, blank=True, db_index=True, verbose_name='事件')
    node_name = models.CharField(max_length=80, db_index=True, verbose_name='节点名称')
    tool_name = models.CharField(max_length=120, db_index=True, verbose_name='工具名称')
    subagent_name = models.CharField(max_length=80, blank=True, db_index=True, verbose_name='调用SubAgent')
    permission_scope = models.CharField(max_length=40, blank=True, verbose_name='权限范围')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS, db_index=True)
    input_summary = models.JSONField(default=dict, blank=True, verbose_name='输入摘要')
    output_summary = models.JSONField(default=dict, blank=True, verbose_name='输出摘要')
    retrieval_trace = models.JSONField(default=dict, blank=True, verbose_name='检索轨迹')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    fallback_reason = models.CharField(max_length=200, blank=True, verbose_name='降级原因')
    latency_ms = models.PositiveIntegerField(null=True, blank=True, verbose_name='耗时毫秒')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '面试Agent工具调用'
        verbose_name_plural = verbose_name
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'tool_name', 'status']),
            models.Index(fields=['session', 'node_name', 'created_at']),
        ]

    def __str__(self):
        return f'{self.session_id} {self.tool_name} {self.status}'


class InterviewAgentMemoryEvent(models.Model):
    class EventType(models.TextChoices):
        OBSERVATION = 'observation', '观察'
        PLAN = 'plan', '计划'
        COVERAGE = 'coverage', '覆盖'
        QUESTION = 'question', '题目'
        ENVIRONMENT = 'environment', '环境'

    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='agent_memory_events',
        verbose_name='面试会话'
    )
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_memory_events',
        verbose_name='关联问题'
    )
    trace = models.ForeignKey(
        InterviewAgentTrace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='memory_events',
        verbose_name='关联轨迹'
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices, db_index=True)
    memory_key = models.CharField(max_length=120, db_index=True, verbose_name='记忆键')
    dedup_key = models.CharField(max_length=64, null=True, blank=True, verbose_name='记忆去重键')
    value_summary = models.JSONField(default=dict, blank=True, verbose_name='记忆摘要')
    importance = models.PositiveSmallIntegerField(default=1, db_index=True, verbose_name='重要性')
    source_node = models.CharField(max_length=80, blank=True, db_index=True, verbose_name='来源节点')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')
    recall_count = models.PositiveIntegerField(default=0, verbose_name='召回次数')
    last_recalled_at = models.DateTimeField(null=True, blank=True, verbose_name='最后召回时间')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '面试Agent记忆事件'
        verbose_name_plural = verbose_name
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'event_type', 'importance']),
            models.Index(fields=['session', 'memory_key', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'dedup_key'],
                condition=models.Q(dedup_key__isnull=False),
                name='uniq_interview_memory_event_dedup',
            ),
        ]

    def __str__(self):
        return f'{self.session_id} {self.event_type} {self.memory_key}'


def interview_media_upload_path(instance, filename):
    return f'interviews/{instance.session_id}/media/{instance.artifact_type}/{filename}'


class InterviewMediaArtifact(models.Model):
    class ArtifactType(models.TextChoices):
        ANSWER_AUDIO = 'answer_audio', '回答音频'
        QUESTION_TTS = 'question_tts', '问题语音'

    class Status(models.TextChoices):
        PENDING = 'pending', '待处理'
        PROCESSING = 'processing', '处理中'
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name='media_artifacts',
        verbose_name='面试会话'
    )
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_artifacts',
        verbose_name='关联问题'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_media_artifacts')
    artifact_type = models.CharField(max_length=32, choices=ArtifactType.choices, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    source_file = models.FileField(upload_to=interview_media_upload_path, null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    transcript_text = models.TextField(blank=True)
    transcript_segments = models.JSONField(default=list, blank=True)
    asr_confidence = models.FloatField(null=True, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    model_slug = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '面试多媒体记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session', 'artifact_type', 'status']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f'{self.session_id} {self.artifact_type} {self.status}'


class EvaluationDataset(models.Model):
    class Visibility(models.TextChoices):
        SHARED = 'shared', '共享'
        PRIVATE = 'private', '私有'

    name = models.CharField(max_length=160, verbose_name='评估数据集名称')
    description = models.TextField(blank=True, verbose_name='说明')
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PRIVATE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluation_datasets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '离线评估数据集'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class EvaluationCase(models.Model):
    dataset = models.ForeignKey(EvaluationDataset, on_delete=models.CASCADE, related_name='cases')
    job_position = models.CharField(max_length=120, verbose_name='岗位')
    jd_text = models.TextField(blank=True, verbose_name='JD')
    resume_text = models.TextField(blank=True, verbose_name='匿名化简历')
    question = models.TextField(verbose_name='问题')
    answer = models.TextField(verbose_name='真实匿名化回答')
    contexts = models.JSONField(default=list, blank=True, verbose_name='检索上下文')
    expected_dimensions = models.JSONField(default=list, blank=True, verbose_name='期望能力标签')
    expected_follow_up = models.TextField(blank=True, verbose_name='期望追问方向')
    ground_truth = models.TextField(blank=True, verbose_name='参考答案/真值')
    expected_document_revision_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name='期望命中的文档修订',
    )
    irrelevant_document_revision_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name='无关文档修订',
    )
    expected_topics = models.JSONField(default=list, blank=True, verbose_name='期望主题')
    is_no_answer = models.BooleanField(default=False, db_index=True, verbose_name='无答案样例')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '离线评估样例'
        verbose_name_plural = verbose_name
        ordering = ['dataset', 'id']

    def __str__(self):
        return f'{self.dataset.name} - {self.job_position}'


class EvaluationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待运行'
        RUNNING = 'running', '运行中'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'

    operation = models.OneToOneField(
        'core.AsyncOperation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluation_run',
        verbose_name='平台异步操作',
    )
    dataset = models.ForeignKey(EvaluationDataset, on_delete=models.CASCADE, related_name='runs')
    template = models.ForeignKey(InterviewTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluation_runs')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    config_snapshot = models.JSONField(default=dict, blank=True, verbose_name='配置快照')
    summary = models.JSONField(default=dict, blank=True, verbose_name='评估摘要')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluation_runs')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '离线评估运行'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.dataset.name} {self.status}'


class EvaluationRunMetric(models.Model):
    run = models.ForeignKey(EvaluationRun, on_delete=models.CASCADE, related_name='metrics')
    case = models.ForeignKey(EvaluationCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='run_metrics')
    metric_name = models.CharField(max_length=100, verbose_name='指标名称')
    score = models.FloatField(null=True, blank=True, verbose_name='指标值')
    detail = models.JSONField(default=dict, blank=True, verbose_name='指标详情')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '离线评估指标'
        verbose_name_plural = verbose_name
        ordering = ['run', 'metric_name', 'id']
