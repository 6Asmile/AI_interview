from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response

from .models import AuthSession, LoginAudit, User
from .cookie_auth import (
    cookie_refresh_value,
    enforce_csrf,
    ensure_csrf_token,
    set_refresh_cookie,
)
from .serializers import UserProfileSerializer
from core.throttles import LoginRateThrottle


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


def record_auth_session(user, refresh, request, event='password_login'):
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''
    AuthSession.objects.update_or_create(
        refresh_jti=str(refresh['jti']),
        defaults={
            'user': user,
            'ip_address': _client_ip(request) if request else None,
            'user_agent': user_agent,
            'device_name': _device_name(user_agent),
            'expires_at': datetime.fromtimestamp(int(refresh['exp']), tz=dt_timezone.utc),
            'revoked_at': None,
        },
    )
    LoginAudit.objects.create(
        user=user,
        email=user.email,
        event=event,
        success=True,
        ip_address=_client_ip(request) if request else None,
        user_agent=user_agent,
    )


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
        record_auth_session(self.user, refresh, request)
        return data


class AuditedTokenObtainPairView(TokenObtainPairView):
    serializer_class = AuditedTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        cookie_mode = request.headers.get('X-Auth-Mode', '').lower() == 'cookie'
        if cookie_mode:
            enforce_csrf(request)
        response = super().post(request, *args, **kwargs)
        refresh_value = response.data.get('refresh') if isinstance(response.data, dict) else None
        if response.status_code == status.HTTP_200_OK and refresh_value:
            set_refresh_cookie(response, refresh_value)
            if cookie_mode:
                response.data.pop('refresh', None)
                response.data['auth_mode'] = 'cookie_refresh'
        return response


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

    def post(self, request, *args, **kwargs):
        cookie_value = cookie_refresh_value(request)
        cookie_mode = bool(cookie_value) and not request.data.get('refresh')
        if cookie_mode:
            enforce_csrf(request)
            payload = {'refresh': cookie_value}
            serializer = self.get_serializer(data=payload)
            serializer.is_valid(raise_exception=True)
            response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        else:
            response = super().post(request, *args, **kwargs)
        new_refresh = response.data.get('refresh') if isinstance(response.data, dict) else None
        if new_refresh:
            set_refresh_cookie(response, new_refresh)
            if cookie_mode or request.headers.get('X-Auth-Mode', '').lower() == 'cookie':
                response.data.pop('refresh', None)
                response.data['auth_mode'] = 'cookie_refresh'
        return response


class CsrfTokenView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'csrf_token': ensure_csrf_token(request)})


class BrowserSessionView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_value = cookie_refresh_value(request)
        if not refresh_value:
            return Response({'code': 'session_not_found', 'message': '浏览器会话不存在。'}, status=status.HTTP_401_UNAUTHORIZED)
        enforce_csrf(request)
        serializer = AuditedTokenRefreshSerializer(data={'refresh': refresh_value}, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        access = str(data['access'])
        access_token = RefreshToken(data.get('refresh') or refresh_value).access_token
        user_id = access_token.get('user_id')
        user = User.objects.filter(pk=user_id, status=User.Status.NORMAL).first()
        if not user:
            return Response({'code': 'session_user_unavailable', 'message': '账号不可用。'}, status=status.HTTP_401_UNAUTHORIZED)
        response = Response({
            'access': access,
            'user': UserProfileSerializer(user, context={'request': request}).data,
            'auth_mode': 'cookie_refresh',
        })
        if data.get('refresh'):
            set_refresh_cookie(response, str(data['refresh']))
        return response
