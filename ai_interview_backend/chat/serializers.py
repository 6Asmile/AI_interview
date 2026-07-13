from rest_framework import serializers

from users.serializers import UserProfileSerializer

from .models import (
    Conversation,
    ConversationParticipantState,
    Message,
    MessageAttachment,
    MessageReport,
    UserBlock,
)


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ['id', 'original_name', 'mime_type', 'size', 'sha256', 'scan_status', 'scan_engine', 'scan_detail', 'file_url', 'expires_at', 'created_at']
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.scan_status != MessageAttachment.ScanStatus.CLEAN or not obj.file:
            return ''
        request = self.context.get('request')
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url


class MessageSerializer(serializers.ModelSerializer):
    sender = UserProfileSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    reply_preview = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'client_message_id', 'sender', 'content', 'message_type', 'file_url',
            'delivery_status', 'reply_to', 'reply_preview', 'attachments', 'metadata',
            'timestamp', 'edited_at', 'revoked_at', 'is_read',
        ]
        read_only_fields = fields

    def get_reply_preview(self, obj):
        if not obj.reply_to:
            return None
        return {
            'id': obj.reply_to_id,
            'sender_id': obj.reply_to.sender_id,
            'content': '消息已撤回' if obj.reply_to.revoked_at else obj.reply_to.content[:120],
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.revoked_at:
            data['content'] = ''
            data['file_url'] = None
            data['attachments'] = []
        return data


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserProfileSerializer(many=True, read_only=True)
    latest_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    participant_state = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'conversation_type', 'title', 'application', 'interview_session',
            'participants', 'updated_at', 'latest_message', 'unread_count', 'participant_state',
        ]

    def get_latest_message(self, obj):
        latest = obj.messages.order_by('-timestamp').first()
        return MessageSerializer(latest, context=self.context).data if latest else None

    def _state(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        return next((state for state in obj.participant_states.all() if state.user_id == request.user.id), None)

    def get_unread_count(self, obj):
        request = self.context.get('request')
        state = self._state(obj)
        queryset = obj.messages.exclude(sender=request.user) if request and request.user.is_authenticated else obj.messages.none()
        if state and state.last_read_message_id:
            queryset = queryset.filter(id__gt=state.last_read_message_id)
        return queryset.count()

    def get_participant_state(self, obj):
        state = self._state(obj)
        return {'muted': state.muted, 'archived': state.archived, 'last_read_message_id': state.last_read_message_id} if state else None


class MessageReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageReport
        fields = ['id', 'message', 'reason', 'detail', 'status', 'created_at', 'resolved_at']
        read_only_fields = ('status', 'created_at', 'resolved_at')


class UserBlockSerializer(serializers.ModelSerializer):
    blocked_user = UserProfileSerializer(source='blocked', read_only=True)

    class Meta:
        model = UserBlock
        fields = ['id', 'blocked', 'blocked_user', 'reason', 'created_at']
        read_only_fields = ('created_at',)
