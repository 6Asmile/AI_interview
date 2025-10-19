from django.contrib import admin
from .models import AIModel, AISetting, Industry, JobPosition

# system/admin.py
@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_slug', 'base_url', 'is_active', 'supports_json_mode')
    list_editable = ('is_active', 'supports_json_mode')
    search_fields = ('name', 'model_slug')

@admin.register(AISetting)
class AISettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'ai_model', 'updated_at')
    # raw_id_fields = ('user',) # raw_id_fields 更适合用户量巨大时，我们可以暂时去掉
    list_filter = ('ai_model',) # 使用 list_filter 替代
    search_fields = ('user__username',) # 允许通过用户名搜索
    # autocomplete_fields 依赖于上面 AIModelAdmin 中的 search_fields
    autocomplete_fields = ('ai_model',)

@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    search_fields = ('name',) # 为 Industry 也加上搜索

@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_filter = ('industry', 'is_active')
    list_display = ('name', 'industry', 'is_active', 'order')
    list_editable = ('industry', 'is_active', 'order')
    search_fields = ('name',)