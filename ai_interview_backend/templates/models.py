import os
import uuid
from django.db import models


# 一个辅助函数，用于生成独特的上传路径
def template_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('resume-templates', instance.slug, filename)


class ResumeTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='模板名称')
    slug = models.SlugField(max_length=100, unique=True, help_text="模板的唯一英文标识，例如 'classic-blue'",
                            verbose_name='模板标识')

    # 模板的 Word (.docx) 源文件
    source_file = models.FileField(upload_to=template_upload_path, null=True, blank=True,
                                   help_text="上传 .docx 格式的模板文件", verbose_name='模板源文件 (.docx)')

    # 模板的预览图
    preview_image = models.ImageField(upload_to=template_upload_path, verbose_name='预览图')

    # 【核心】存储从 Word 解析出的、前端可用的 JSON 结构
    # 这个字段将由后台服务自动填充
    structure_json = models.JSONField(default=dict, blank=True, help_text="由系统自动从源文件解析生成，请勿手动修改",
                                      verbose_name='模板结构 (JSON)')

    description = models.TextField(blank=True, verbose_name='模板描述')
    is_public = models.BooleanField(default=False, help_text="勾选后，所有用户都可以在模板市场看到此模板",
                                    verbose_name='是否发布')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '简历模板'
        verbose_name_plural = verbose_name
        ordering = ['order']

    def __str__(self):
        return self.name