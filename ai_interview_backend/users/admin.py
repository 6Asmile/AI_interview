# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import AuthSession, LoginAudit, NotificationPreference, PrivacyRequest, User


# 我们使用 UserAdmin 来获得一个功能更丰富的用户管理界面
# list_display 可以让我们在列表页看到更多信息
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['email', 'username', 'role', 'status', 'is_staff', 'date_joined']

    # 让后台表单的字段布局更合理
    # 这里我们继承了 UserAdmin 的 fieldsets 并做了微调
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('email', 'phone', 'avatar', 'role', 'headline', 'location', 'years_experience', 'target_roles', 'skills_profile', 'availability', 'profile_visibility')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


# 注册你的 User 模型和自定义的 Admin 类
admin.site.register(User, CustomUserAdmin)
admin.site.register(NotificationPreference)
admin.site.register(AuthSession)


@admin.register(LoginAudit)
class LoginAuditAdmin(admin.ModelAdmin):
    list_display = ('email', 'event', 'success', 'ip_address', 'created_at')
    list_filter = ('event', 'success')
    search_fields = ('email', 'user__email', 'ip_address')
    readonly_fields = [field.name for field in LoginAudit._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(PrivacyRequest)
class PrivacyRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'request_type', 'status', 'created_at', 'completed_at')
    list_filter = ('request_type', 'status')
    search_fields = ('user__email', 'reason')
