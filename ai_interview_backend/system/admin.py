from django.contrib import admin
from .models import AISetting, Industry, JobPosition

@admin.register(AISetting)
class AISettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'ai_model', 'updated_at')
    search_fields = ('user__username',)

@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'order')
    list_editable = ('is_active', 'order')

@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    # 让我们可以按行业筛选岗位
    list_filter = ('industry', 'is_active')
    list_display = ('name', 'industry', 'is_active', 'order')
    list_editable = ('industry', 'is_active', 'order')
    search_fields = ('name',)