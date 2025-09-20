# interviews/admin.py
from django.contrib import admin
from .models import InterviewSession, InterviewQuestion

class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0  # 默认不显示额外空行
    readonly_fields = ('created_at', 'answered_at', 'evaluated_at')

@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('job_position', 'user', 'status', 'difficulty', 'created_at')
    list_filter = ('status', 'difficulty', 'user')
    search_fields = ('job_position', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'finished_at')
    inlines = [InterviewQuestionInline] # 在会话详情页直接显示关联的问题

@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('sequence', 'question_text', 'session', 'score', 'answered_at')
    list_filter = ('session__job_position',)
    search_fields = ('question_text', 'answer_text')