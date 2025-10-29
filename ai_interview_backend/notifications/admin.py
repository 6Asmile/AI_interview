from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'verb', 'actor', 'target', 'timestamp', 'is_read')
    list_filter = ('verb', 'is_read', 'timestamp')
    search_fields = ('recipient__username',)
    readonly_fields = ('actor_content_type', 'actor_object_id', 'target_content_type', 'target_object_id', 'action_object_content_type', 'action_object_object_id')