# system/models.py
from django.db import models
from users.models import User


# 1. AIModel 模型
class AIModel(models.Model):
    name = models.CharField(max_length=100, verbose_name='模型显示名称')
    model_slug = models.CharField(max_length=100, unique=True, verbose_name='模型调用标识')
    base_url = models.URLField(max_length=255, verbose_name='API Base URL')
    description = models.TextField(blank=True, verbose_name='模型描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    # 【核心新增】新增一个布尔字段来标记是否支持 JSON Mode
    supports_json_mode = models.BooleanField(default=True, verbose_name='支持 JSON 模式')
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
        verbose_name='默认AI模型'
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