# ai_interview_backend/reports/admin.py

from django.contrib import admin
from .models import ResumeAnalysisReport


@admin.register(ResumeAnalysisReport)
class ResumeAnalysisReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'resume', 'user', 'overall_score', 'created_at')
    list_filter = ('user', 'created_at')
    search_fields = ('resume__title', 'user__email', 'jd_text')
    readonly_fields = ('id', 'created_at', 'updated_at')

    # 为了方便，可以直接在后台看到JSON内容
    fieldsets = (
        (None, {
            'fields': ('id', 'user', 'resume', 'overall_score')
        }),
        ('报告详情', {
            'classes': ('collapse',),  # 可折叠
            'fields': ('jd_text', 'report_data'),
        }),
    )