from django.contrib import admin
from .models import (
    AIModel,
    AISetting,
    Industry,
    JobPosition,
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ProviderCredential,
    RoutePolicy,
    RoutePolicyTarget,
    UsageBudget,
)

# system/admin.py
@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_slug', 'provider', 'model_type', 'base_url', 'dimension', 'is_active', 'supports_json_mode')
    list_editable = ('is_active', 'supports_json_mode')
    list_filter = ('provider', 'model_type', 'is_active')
    search_fields = ('name', 'model_slug', 'provider')

@admin.register(AISetting)
class AISettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'chat_model', 'embedding_model', 'rerank_model', 'asr_model', 'tts_model', 'updated_at')
    # raw_id_fields = ('user',) # raw_id_fields 更适合用户量巨大时，我们可以暂时去掉
    list_filter = ('chat_model', 'embedding_model', 'rerank_model', 'asr_model', 'tts_model') # 使用 list_filter 替代
    search_fields = ('user__username',) # 允许通过用户名搜索
    # autocomplete_fields 依赖于上面 AIModelAdmin 中的 search_fields
    autocomplete_fields = ('ai_model', 'chat_model', 'embedding_model', 'rerank_model', 'asr_model', 'tts_model')

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


@admin.register(ProviderCredential)
class ProviderCredentialAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'scope', 'user', 'legacy_model', 'secret_hint', 'is_active', 'updated_at')
    list_filter = ('scope', 'provider', 'is_active')
    search_fields = ('name', 'user__email', 'legacy_model__model_slug')
    exclude = ('encrypted_secret',)


@admin.register(ModelDeployment)
class ModelDeploymentAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'remote_model', 'model_type', 'priority', 'is_active', 'last_health_status')
    list_filter = ('provider', 'model_type', 'is_active', 'last_health_status')
    search_fields = ('name', 'remote_model')


class RoutePolicyTargetInline(admin.TabularInline):
    model = RoutePolicyTarget
    extra = 0


@admin.register(RoutePolicy)
class RoutePolicyAdmin(admin.ModelAdmin):
    list_display = ('alias', 'strategy', 'max_attempts', 'total_timeout_seconds', 'is_active')
    inlines = [RoutePolicyTargetInline]


admin.site.register(ModelAlias)
admin.site.register(UsageBudget)


@admin.register(ModelRequestLedger)
class ModelRequestLedgerAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'user', 'task_name', 'status', 'deployment', 'latency_ms', 'estimated_cost', 'created_at')
    list_filter = ('status', 'task_name', 'deployment')
    search_fields = ('request_id', 'user__email', 'error_code')
    readonly_fields = [field.name for field in ModelRequestLedger._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
