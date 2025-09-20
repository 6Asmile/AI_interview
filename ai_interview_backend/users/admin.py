# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


# 我们使用 UserAdmin 来获得一个功能更丰富的用户管理界面
# list_display 可以让我们在列表页看到更多信息
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['email', 'username', 'role', 'status', 'is_staff', 'date_joined']

    # 让后台表单的字段布局更合理
    # 这里我们继承了 UserAdmin 的 fieldsets 并做了微调
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('email', 'phone', 'avatar', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


# 注册你的 User 模型和自定义的 Admin 类
admin.site.register(User, CustomUserAdmin)