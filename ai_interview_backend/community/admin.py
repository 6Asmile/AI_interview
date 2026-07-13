from django.contrib import admin

from .models import CommunityIdentity, CommunityTopicLink, CommunityWebhookEvent


admin.site.register(CommunityIdentity)
admin.site.register(CommunityTopicLink)


@admin.register(CommunityWebhookEvent)
class CommunityWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'status', 'received_at', 'processed_at')
    list_filter = ('event_type', 'status')
    search_fields = ('event_id', 'error_message')
    readonly_fields = [field.name for field in CommunityWebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False

