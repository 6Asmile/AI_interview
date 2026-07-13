from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import serializers

from .models import AuthSession, LoginAudit, User


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')) or None


def _device_name(user_agent: str) -> str:
    value = (user_agent or '').lower()
    if 'mobile' in value or 'android' in value or 'iphone' in value:
        return '移动设备'
    if 'windows' in value:
        return 'Windows'
    if 'macintosh' in value or 'mac os' in value:
        return 'macOS'
    return '浏览器会话'


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    mfa_code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        request = self.context.get('request')
        email = str(attrs.get(self.username_field) or '')
        mfa_code = str(attrs.pop('mfa_code', '') or '').strip()
        try:
            data = super().validate(attrs)
            from allauth.mfa.models import Authenticator
            authenticator = Authenticator.objects.filter(user=self.user, type=Authenticator.Type.TOTP).first()
            if authenticator:
                recovery = Authenticator.objects.filter(user=self.user, type=Authenticator.Type.RECOVERY_CODES).first()
                valid = bool(mfa_code) and (
                    authenticator.wrap().validate_code(mfa_code)
                    or (recovery and recovery.wrap().validate_code(mfa_code))
                )
                if not valid:
                    raise serializers.ValidationError({'mfa_code': '需要有效的双重验证代码。', 'mfa_required': True})
        except Exception as exc:
            LoginAudit.objects.create(
                user=User.objects.filter(email=email).first(),
                email=email,
                event='password_login',
                success=False,
                ip_address=_client_ip(request) if request else None,
                user_agent=(request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''),
                reason=type(exc).__name__,
            )
            raise
        refresh = RefreshToken(data['refresh'])
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''
        AuthSession.objects.update_or_create(
            refresh_jti=str(refresh['jti']),
            defaults={
                'user': self.user,
                'ip_address': _client_ip(request) if request else None,
                'user_agent': user_agent,
                'device_name': _device_name(user_agent),
                'expires_at': datetime.fromtimestamp(int(refresh['exp']), tz=dt_timezone.utc),
                'revoked_at': None,
            },
        )
        LoginAudit.objects.create(
            user=self.user,
            email=self.user.email,
            event='password_login',
            success=True,
            ip_address=_client_ip(request) if request else None,
            user_agent=user_agent,
        )
        return data


class AuditedTokenObtainPairView(TokenObtainPairView):
    serializer_class = AuditedTokenObtainPairSerializer


class AuditedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        old_refresh = RefreshToken(attrs['refresh'])
        old_jti = str(old_refresh['jti'])
        data = super().validate(attrs)
        session = AuthSession.objects.filter(refresh_jti=old_jti, revoked_at__isnull=True).first()
        if session:
            if data.get('refresh'):
                new_refresh = RefreshToken(data['refresh'])
                session.refresh_jti = str(new_refresh['jti'])
                session.expires_at = datetime.fromtimestamp(int(new_refresh['exp']), tz=dt_timezone.utc)
            session.last_seen_at = timezone.now()
            session.save(update_fields=['refresh_jti', 'expires_at', 'last_seen_at'])
        return data


class AuditedTokenRefreshView(TokenRefreshView):
    serializer_class = AuditedTokenRefreshSerializer
