from django.db import models
from users.models import User


class Resume(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'  # 新增：在线编辑状态
        PUBLISHED = 'published', '已发布'  # 新增：完成编辑
        PARSED = 'parsed', '（文件）已解析'
        FAILED = 'failed', '（文件）解析失败'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumes', verbose_name='所属用户')
    title = models.CharField(max_length=200, verbose_name='简历标题')

    # --- 文件上传相关字段 (保留，但设为可选) ---
    file = models.FileField(upload_to='resumes/', null=True, blank=True, verbose_name='上传的简历文件')
    parsed_content = models.TextField(blank=True, verbose_name='解析后的文本内容')

    # --- 在线编辑相关字段 ---
    # 个人信息
    full_name = models.CharField(max_length=100, blank=True, verbose_name='姓名')
    phone = models.CharField(max_length=20, blank=True, verbose_name='电话')
    email = models.EmailField(blank=True, verbose_name='邮箱')
    job_title = models.CharField(max_length=100, blank=True, verbose_name='期望职位')
    city = models.CharField(max_length=50, blank=True, verbose_name='城市')
    summary = models.TextField(blank=True, verbose_name='个人总结')

    # --- AI 优化与状态 ---
    is_default = models.BooleanField(default=False, verbose_name='是否默认简历')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name='状态')
    optimization_suggestions = models.JSONField(null=True, blank=True, verbose_name='优化建议')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    # 【新增】一个属性方法，用于生成文件的完整 URL
    @property
    def file_url(self):
        if self.file:
            return self.file.url
        return None

    class Meta:
        verbose_name = '简历'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.username} - {self.title}'


# --- 新增的结构化数据模型 ---

class Education(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='educations', verbose_name='所属简历')
    school = models.CharField(max_length=100, verbose_name='学校名称')
    degree = models.CharField(max_length=50, verbose_name='学位')
    major = models.CharField(max_length=100, verbose_name='专业')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(verbose_name='结束日期')

    class Meta:
        verbose_name = '教育经历'
        verbose_name_plural = verbose_name
        ordering = ['-end_date']


class WorkExperience(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='work_experiences',
                               verbose_name='所属简历')
    company = models.CharField(max_length=100, verbose_name='公司名称')
    position = models.CharField(max_length=100, verbose_name='职位')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    description = models.TextField(verbose_name='工作描述')

    class Meta:
        verbose_name = '工作经历'
        verbose_name_plural = verbose_name
        ordering = ['-start_date']


class ProjectExperience(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='project_experiences',
                               verbose_name='所属简历')
    project_name = models.CharField(max_length=100, verbose_name='项目名称')
    role = models.CharField(max_length=100, verbose_name='担任角色')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    description = models.TextField(verbose_name='项目描述')

    class Meta:
        verbose_name = '项目经历'
        verbose_name_plural = verbose_name
        ordering = ['-start_date']


class Skill(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='skills', verbose_name='所属简历')
    skill_name = models.CharField(max_length=100, verbose_name='技能名称')
    proficiency = models.CharField(max_length=50, blank=True, verbose_name='熟练度')  # e.g., 熟练, 精通

    class Meta:
        verbose_name = '专业技能'
        verbose_name_plural = verbose_name