# users/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser

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