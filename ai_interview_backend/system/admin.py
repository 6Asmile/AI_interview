# system/admin.py
from django.contrib import admin
from .models import AISetting

@admin.register(AISetting)
class AISettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'ai_model', 'updated_at')
    search_fields = ('user__username',)