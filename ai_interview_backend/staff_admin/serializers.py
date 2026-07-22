from rest_framework import serializers

from .models import AdminAuditEvent, StaffAccount, StaffRole


class StaffRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRole
        fields = ['slug', 'name', 'permissions']


class StaffAccountSerializer(serializers.ModelSerializer):
    roles = StaffRoleSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()
    mfa_enabled = serializers.SerializerMethodField()
    invitation = serializers.SerializerMethodField()
    active_sessions = serializers.SerializerMethodField()

    class Meta:
        model = StaffAccount
        fields = [
            'id', 'email', 'display_name', 'status', 'roles', 'permissions', 'mfa_enabled',
            'must_change_password', 'active_sessions', 'invitation', 'last_login', 'created_at',
        ]

    def get_permissions(self, obj):
        return sorted(obj.permission_set())

    def get_mfa_enabled(self, obj):
        return obj.mfa_devices.filter(confirmed_at__isnull=False).exists()

    def get_active_sessions(self, obj):
        from django.utils import timezone
        return obj.sessions.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).count()

    def get_invitation(self, obj):
        try:
            invitation = obj.invitation
        except Exception:
            return None
        return {
            'id': str(invitation.id), 'status': invitation.status, 'expires_at': invitation.expires_at,
            'sent_count': invitation.sent_count, 'last_sent_at': invitation.last_sent_at,
        }


class AdminAuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AdminAuditEvent
        fields = [
            'id', 'actor', 'action', 'resource_type', 'resource_id', 'operation_reason',
            'request_id', 'before_summary', 'after_summary', 'metadata', 'previous_hash',
            'event_hash', 'created_at',
        ]

    def get_actor(self, obj):
        return {'id': str(obj.actor_id), 'email': obj.actor.email, 'display_name': obj.actor.display_name} if obj.actor else None
