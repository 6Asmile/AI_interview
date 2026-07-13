# system/models.py
from django.db import models
from users.models import User
import uuid


# 1. AIModel 模型
class AIModel(models.Model):
    class ModelType(models.TextChoices):
        CHAT = 'chat', '对话模型'
        EMBEDDING = 'embedding', 'Embedding模型'
        RERANK = 'rerank', 'Rerank模型'
        ASR = 'asr', '语音识别模型'
        TTS = 'tts', '语音合成模型'

    name = models.CharField(max_length=100, verbose_name='模型显示名称')
    model_slug = models.CharField(max_length=100, unique=True, verbose_name='模型调用标识')
    base_url = models.URLField(max_length=255, verbose_name='API Base URL')
    provider = models.CharField(max_length=50, default='openai_compatible', verbose_name='模型供应商')
    model_type = models.CharField(
        max_length=20,
        choices=ModelType.choices,
        default=ModelType.CHAT,
        db_index=True,
        verbose_name='模型类型'
    )
    description = models.TextField(blank=True, verbose_name='模型描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    # 【核心新增】新增一个布尔字段来标记是否支持 JSON Mode
    supports_json_mode = models.BooleanField(default=True, verbose_name='支持 JSON 模式')
    dimension = models.PositiveIntegerField(null=True, blank=True, verbose_name='向量维度')
    class Meta:
        verbose_name = 'AI 模型'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


# 2. AISetting 模型

class AISetting(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ai_setting', verbose_name='所属用户')

    # 【核心修改】'ai_model' 现在代表用户选择的“默认模型”
    ai_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legacy_settings',
        verbose_name='默认AI模型'
    )
    chat_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_settings',
        limit_choices_to={'model_type': AIModel.ModelType.CHAT},
        verbose_name='默认对话模型'
    )
    embedding_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='embedding_settings',
        limit_choices_to={'model_type': AIModel.ModelType.EMBEDDING},
        verbose_name='默认Embedding模型'
    )
    rerank_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rerank_settings',
        limit_choices_to={'model_type': AIModel.ModelType.RERANK},
        verbose_name='默认Rerank模型'
    )
    asr_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asr_settings',
        limit_choices_to={'model_type': AIModel.ModelType.ASR},
        verbose_name='默认ASR模型'
    )
    tts_model = models.ForeignKey(
        AIModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tts_settings',
        limit_choices_to={'model_type': AIModel.ModelType.TTS},
        verbose_name='默认TTS模型'
    )

    # 【核心修改】将单一 api_key 替换为 JSONField 来存储多个 key
    # 结构: {"model_id_1": "key_1", "model_id_2": "key_2", ...}
    api_keys = models.JSONField(default=dict, blank=True, verbose_name='API Keys 映射')

    # 原有的 api_key 字段可以删除了
    # api_key = models.CharField(max_length=255, blank=True, verbose_name='API Key')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = 'AI 设置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user.username} 的 AI 设置"

# 3. Industry 模型
class Industry(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='行业名称')
    description = models.TextField(blank=True, verbose_name='行业描述')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')

    class Meta:
        verbose_name = '行业分类'
        verbose_name_plural = verbose_name
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


# 4. JobPosition 模型
class JobPosition(models.Model):
    industry = models.ForeignKey(
        Industry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_positions',
        verbose_name='所属行业'
    )
    name = models.CharField(max_length=100, unique=True, verbose_name='岗位名称')
    description = models.TextField(blank=True, verbose_name='岗位描述')
    icon_svg = models.TextField(blank=True, verbose_name='图标 SVG 代码')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')

    class Meta:
        verbose_name = '面试岗位'
        verbose_name_plural = verbose_name
        ordering = ['industry__order', 'order', 'name']

    def __str__(self):
        return self.name


class ProviderCredential(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = 'platform', '平台凭据'
        BYOK = 'byok', '用户自带密钥'

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='provider_credentials')
    legacy_model = models.ForeignKey(AIModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='credentials')
    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=50, default='openai_compatible', db_index=True)
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.BYOK, db_index=True)
    encrypted_secret = models.TextField(blank=True)
    secret_hint = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scope', 'provider', 'name']
        indexes = [models.Index(fields=['user', 'provider', 'scope', 'is_active'])]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.scope == self.Scope.PLATFORM and self.user_id:
            raise ValidationError({'user': '平台凭据不能绑定普通用户。'})
        if self.scope == self.Scope.BYOK and not self.user_id:
            raise ValidationError({'user': 'BYOK 凭据必须绑定用户。'})

    def set_secret(self, value: str):
        from .credentials import encrypt_secret, secret_hint
        self.encrypted_secret = encrypt_secret(value)
        self.secret_hint = secret_hint(value)

    def get_secret(self) -> str:
        from .credentials import decrypt_secret
        return decrypt_secret(self.encrypted_secret)

    def __str__(self):
        return f'{self.name} ({self.get_scope_display()})'


class ModelDeployment(models.Model):
    name = models.CharField(max_length=120, unique=True)
    provider = models.CharField(max_length=50, db_index=True)
    remote_model = models.CharField(max_length=160)
    model_type = models.CharField(max_length=20, choices=AIModel.ModelType.choices, db_index=True)
    base_url = models.URLField(max_length=500)
    credential = models.ForeignKey(ProviderCredential, on_delete=models.SET_NULL, null=True, blank=True, related_name='deployments')
    capabilities = models.JSONField(default=dict, blank=True)
    context_window = models.PositiveIntegerField(null=True, blank=True)
    input_price_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    output_price_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    priority = models.PositiveIntegerField(default=100)
    timeout_seconds = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True, db_index=True)
    last_health_status = models.CharField(max_length=24, blank=True)
    last_health_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']

    def __str__(self):
        return self.name


class ModelAlias(models.Model):
    slug = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=120)
    model_type = models.CharField(max_length=20, choices=AIModel.ModelType.choices, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['model_type', 'slug']

    def __str__(self):
        return self.slug


class RoutePolicy(models.Model):
    class Strategy(models.TextChoices):
        PRIORITY = 'priority', '按优先级故障转移'
        WEIGHTED = 'weighted', '加权选择'

    alias = models.OneToOneField(ModelAlias, on_delete=models.CASCADE, related_name='route_policy')
    strategy = models.CharField(max_length=16, choices=Strategy.choices, default=Strategy.PRIORITY)
    total_timeout_seconds = models.PositiveIntegerField(default=45)
    max_attempts = models.PositiveIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RoutePolicyTarget(models.Model):
    policy = models.ForeignKey(RoutePolicy, on_delete=models.CASCADE, related_name='targets')
    deployment = models.ForeignKey(ModelDeployment, on_delete=models.CASCADE, related_name='route_targets')
    order = models.PositiveIntegerField(default=0)
    weight = models.PositiveIntegerField(default=100)
    retry_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'deployment__priority']
        constraints = [models.UniqueConstraint(fields=['policy', 'deployment'], name='uniq_policy_deployment')]


class UsageBudget(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='model_usage_budget')
    monthly_token_limit = models.PositiveBigIntegerField(default=0, help_text='0 表示不限制')
    monthly_cost_limit = models.DecimalField(max_digits=12, decimal_places=4, default=0, help_text='0 表示不限制')
    period_start = models.DateField()
    used_input_tokens = models.PositiveBigIntegerField(default=0)
    used_output_tokens = models.PositiveBigIntegerField(default=0)
    used_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class ModelRequestLedger(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running', '运行中'
        SUCCEEDED = 'succeeded', '成功'
        FAILED = 'failed', '失败'
        REJECTED = 'rejected', '额度拒绝'

    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='model_request_ledgers')
    alias = models.ForeignKey(ModelAlias, on_delete=models.SET_NULL, null=True, blank=True, related_name='request_ledgers')
    deployment = models.ForeignKey(ModelDeployment, on_delete=models.SET_NULL, null=True, blank=True, related_name='request_ledgers')
    task_name = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING, db_index=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    fallback_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'task_name', 'created_at'])]
