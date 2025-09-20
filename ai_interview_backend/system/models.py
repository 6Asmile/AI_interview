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