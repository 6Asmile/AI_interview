# resumes/models.py
from django.db import models
from users.models import User  # 从 users 应用导入 User 模型


class Resume(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待解析'
        PARSED = 'parsed', '已解析'
        FAILED = 'failed', '解析失败'

    # 核心字段
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumes', verbose_name='所属用户')
    title = models.CharField(max_length=200, verbose_name='简历标题')
    # 将 file_url 修改为 FileField
    file = models.FileField(upload_to='resumes/', verbose_name='简历文件')
    # file_url = models.CharField(max_length=255, verbose_name='文件存储 URL')  # 暂时先存URL，后续集成对象存储

    # 辅助字段
    file_type = models.CharField(max_length=20, verbose_name='文件类型')
    file_size = models.IntegerField(null=True, blank=True, verbose_name='文件大小 (KB)')
    is_default = models.BooleanField(default=False, verbose_name='是否默认简历')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='状态'
    )

    # 自动生成的时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    # AI相关字段 (暂时留空，后续填充)
    parsed_content = models.TextField(blank=True, verbose_name='解析后的文本内容')
    optimization_suggestions = models.TextField(blank=True, verbose_name='优化建议')

    class Meta:
        verbose_name = '简历'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']  # 默认按创建时间倒序排列

    def __str__(self):
        return f'{self.user.username} - {self.title}'