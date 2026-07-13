from django.contrib import admin

from .models import ApplicationEvent, CareerFact, JobApplication, JobTarget, LearningTask


@admin.register(CareerFact)
class CareerFactAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'fact_type', 'verification_status', 'source_type', 'updated_at')
    list_filter = ('fact_type', 'verification_status', 'source_type')
    search_fields = ('title', 'organization', 'role', 'user__email')


@admin.register(JobTarget)
class JobTargetAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'position_name', 'user', 'status', 'deadline', 'updated_at')
    list_filter = ('status', 'deadline')
    search_fields = ('company_name', 'position_name', 'user__email')


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('job_target', 'user', 'status', 'next_action_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('job_target__company_name', 'job_target__position_name', 'user__email')


admin.site.register(ApplicationEvent)
admin.site.register(LearningTask)

