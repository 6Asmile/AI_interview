# users/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class User(AbstractUser):
    """
    自定义用户模型
    """
    class Role(models.TextChoices):
        CANDIDATE = 'candidate', '求职者'
        HR = 'hr', '企业HR'
        ADMIN = 'admin', '管理员'

    class Status(models.IntegerChoices):
        DISABLED = 0, '禁用'
        NORMAL = 1, '正常'

    # 移除 first_name 和 last_name 字段，如果不需要的话
    first_name = None
    last_name = None

    # 邮箱应该是唯一的，用于登录
    email = models.EmailField(unique=True, verbose_name='邮箱')

    # 额外添加的字段
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name='手机号')
    # 使用 ImageField 来处理图片上传
    # upload_to='avatars/' 指定了图片将被上传到 MEDIA_ROOT/avatars/ 目录下
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='头像')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CANDIDATE, verbose_name='角色')
    status = models.IntegerField(choices=Status.choices, default=Status.NORMAL, verbose_name='状态')
    headline = models.CharField(max_length=160, blank=True, verbose_name='职业标题')
    location = models.CharField(max_length=120, blank=True, verbose_name='所在地区')
    years_experience = models.PositiveSmallIntegerField(default=0, verbose_name='工作年限')
    target_roles = models.JSONField(default=list, blank=True, verbose_name='目标岗位')
    skills_profile = models.JSONField(default=list, blank=True, verbose_name='技能画像')
    availability = models.CharField(max_length=80, blank=True, verbose_name='求职状态')
    profile_visibility = models.CharField(
        max_length=16,
        choices=[('private', '仅自己'), ('community', '社区可见'), ('public', '公开')],
        default='private',
        verbose_name='资料可见性',
    )

    # # 关联企业，这里我们先用字符串定义，避免循环导入问题
    # # 等到创建了 Company 模型后再正式关联
    # company = models.ForeignKey(
    #     'companies.Company',  # 假设未来会有一个 companies 应用和 Company 模型
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     verbose_name='所属企业'
    # )

    # last_login 字段已由 AbstractUser 提供
    # created_at 和 updated_at 已由 AbstractUser 的 date_joined 和我们下面定义的 auto_now 字段处理
    # 我们使用 date_joined 作为 created_at，并添加一个 updated_at 字段
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')



    # 指定使用 email 字段作为用户名字段进行认证
    USERNAME_FIELD = 'email'
    # 创建超级用户时需要填写的字段，移除 username
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


class NotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preference')
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    interview_reminders = models.BooleanField(default=True)
    application_updates = models.BooleanField(default=True)
    community_updates = models.BooleanField(default=True)
    direct_messages = models.BooleanField(default=True)
    digest_frequency = models.CharField(
        max_length=16,
        choices=[('none', '不汇总'), ('daily', '每日'), ('weekly', '每周')],
        default='weekly',
    )
    quiet_hours = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_sessions')
    refresh_jti = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    device_name = models.CharField(max_length=120, blank=True)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen_at']


class LoginAudit(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_audits')
    email = models.EmailField(blank=True)
    event = models.CharField(max_length=32, db_index=True)
    success = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    reason = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class PrivacyRequest(models.Model):
    class RequestType(models.TextChoices):
        EXPORT = 'export', '导出数据'
        DELETE = 'delete', '注销账号'

    class Status(models.TextChoices):
        PENDING = 'pending', '待处理'
        COMPLETED = 'completed', '已完成'
        REJECTED = 'rejected', '已拒绝'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='privacy_requests')
    request_type = models.CharField(max_length=16, choices=RequestType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
