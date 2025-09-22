# system/models.py
from django.db import models
from users.models import User



class AISetting(models.Model):
    # 使用 OneToOneField 确保一个用户只有一套AI配置
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ai_setting', verbose_name='所属用户')

    # 为了未来的扩展性，我们使用 choices
    class AIModel(models.TextChoices):
        DEEPSEEK_CHAT = 'deepseek-chat', 'DeepSeek Chat'
        # 以后可以添加 GPT_4, QWEN_MAX 等

    ai_model = models.CharField(
        max_length=50,
        choices=AIModel.choices,
        default=AIModel.DEEPSEEK_CHAT,
        verbose_name='AI 模型'
    )
    api_key = models.CharField(max_length=255, blank=True, verbose_name='API Key')

    # 以后可以添加 base_url, temperature 等更多自定义设置

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = 'AI 设置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user.username} 的 AI 设置"


# 1. 新增 Industry 模型
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

class JobPosition(models.Model):
    # 2. 新增一个外键字段来关联 Industry
    industry = models.ForeignKey(
        Industry,
        on_delete=models.SET_NULL, # 如果行业被删除，岗位不删除，只是关联变为空
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
        ordering = ['industry__order', 'order', 'name'] # 优先按行业排序

    def __str__(self):
        return self.name