# ai_interview_backend/chat/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    """
    在对话详情页中内联显示消息记录
    """
    model = Message
    extra = 0  # 不显示额外的空行
    readonly_fields = ('sender', 'message_type', 'content_preview', 'timestamp', 'is_read')
    fields = ('sender', 'message_type', 'content', 'content_preview', 'timestamp', 'is_read')
    ordering = ('timestamp',)
    can_delete = True  # 允许管理员删除单条违规消息

    def content_preview(self, obj):
        """内联视图中的富媒体预览"""
        if obj.message_type == 'image' and obj.file_url:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 100px;" />', obj.file_url)
        elif obj.message_type == 'file' and obj.file_url:
            return format_html('<a href="{}" target="_blank">下载文件</a>', obj.file_url)
        return obj.content

    content_preview.short_description = "内容/预览"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_participants', 'updated_at', 'created_at')
    list_filter = ('updated_at',)
    search_fields = ('participants__username', 'participants__email')
    readonly_fields = ('created_at', 'updated_at')

    # 【核心】将消息记录作为内联元素显示
    inlines = [MessageInline]

    def get_participants(self, obj):
        """
        将多对多字段转换为字符串显示在列表页
        """
        return ", ".join([user.username for user in obj.participants.all()])

    get_participants.short_description = "参与者"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
    'id', 'sender', 'get_conversation_id', 'message_type', 'short_content', 'preview_file', 'timestamp', 'is_read')
    list_filter = ('message_type', 'is_read', 'timestamp', 'sender')
    search_fields = ('content', 'sender__username')
    readonly_fields = ('timestamp',)
    # date_hierarchy = 'timestamp'  # 顶部显示时间层级导航

    def get_conversation_id(self, obj):
        return obj.conversation.id

    get_conversation_id.short_description = "对话ID"

    def short_content(self, obj):
        """截断显示过长的文本消息"""
        if obj.message_type == 'text':
            return (obj.content[:50] + '...') if len(obj.content) > 50 else obj.content
        return f"[{obj.get_message_type_display()}]"

    short_content.short_description = "内容摘要"

    def preview_file(self, obj):
        """列表页的富媒体预览"""
        if obj.message_type == 'image' and obj.file_url:
            # 显示图片缩略图
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 40px; border-radius: 4px;" /></a>',
                obj.file_url, obj.file_url)
        elif obj.message_type == 'file' and obj.file_url:
            # 显示文件链接图标
            return format_html('<a href="{}" target="_blank" style="color: #409EFF;">📄 下载</a>', obj.file_url)
        elif obj.message_type == 'voice':
            return "🎤 语音"
        elif obj.message_type == 'video':
            return "🎬 视频"
        return "-"

    preview_file.short_description = "媒体预览"