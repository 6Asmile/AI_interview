from django.contrib import admin

from .models import AdminAuditEvent, StaffAccount, StaffInvitation, StaffMFADevice, StaffRole, StaffSession


@admin.register(StaffAccount)
class StaffAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'display_name', 'status', 'must_change_password', 'last_login', 'created_at')
    list_filter = ('status', 'must_change_password')
    search_fields = ('email', 'display_name')
    filter_horizontal = ('roles',)
    readonly_fields = ('password', 'last_login', 'last_login_ip', 'created_at', 'updated_at')


admin.site.register(StaffRole)
admin.site.register(StaffSession)
admin.site.register(StaffMFADevice)
admin.site.register(StaffInvitation)
admin.site.register(AdminAuditEvent)
