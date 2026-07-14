import json
import base64
from io import BytesIO
from urllib.parse import quote

from allauth.socialaccount.models import SocialAccount
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import cache
from rest_framework import views, status, generics, permissions
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser, FormParser
from .services import send_verification_code
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .models import AuthSession, NotificationPreference, PrivacyRequest, User
from .serializers import (
    AuthSessionSerializer,
    NotificationPreferenceSerializer,
    PasswordChangeSerializer,
    PrivacyRequestSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)

# --- 验证码发送 ---
class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class SendCodeView(views.APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        if send_verification_code(email):
            return Response({"message": "验证码已成功发送，请注意查收。"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "邮件发送失败，请稍后再试或联系管理员。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- 用户注册 ---
class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

# --- 个人信息管理 ---
class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user


class OnboardingCompleteView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        user.onboarding_step = 'completed'
        user.onboarding_completed_at = timezone.now()
        user.save(update_fields=['onboarding_step', 'onboarding_completed_at', 'updated_at'])
        return Response(UserProfileSerializer(user, context={'request': request}).data)

# --- 头像上传 ---
class AvatarUploadView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('avatar')
        if not file_obj:
            return Response({'error': '没有提供头像文件'}, status=status.HTTP_400_BAD_REQUEST)
        if file_obj.size > 2 * 1024 * 1024:
            return Response({'error': '头像文件不能超过 2MB'}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        user.avatar = file_obj
        user.save()
        return Response({'avatar_url': user.avatar.url}, status=status.HTTP_200_OK)

# --- 【核心修正】确保密码修改视图在这里定义 ---
class PasswordChangeView(generics.GenericAPIView):
    """
    处理用户设置/修改密码。
    POST /api/v1/auth/password/change/
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "密码已成功更新。"}, status=status.HTTP_200_OK)


# 【新增】手动处理解绑的 API 视图
class SocialAccountDisconnectView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # account_id 将从 URL 中捕获
        account_id = self.kwargs.get('account_id')
        if not account_id:
            return Response({"error": "Account ID not provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 确保用户只能解绑自己的社交账户
            social_account = SocialAccount.objects.get(id=account_id, user=request.user)
            social_account.delete()
            return Response({"message": "账户已成功解绑。"}, status=status.HTTP_200_OK)
        except SocialAccount.DoesNotExist:
            return Response({"error": "请求的社交账户不存在或不属于您。"}, status=status.HTTP_404_NOT_FOUND)


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return obj


class AuthSessionListView(generics.ListAPIView):
    serializer_class = AuthSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AuthSession.objects.filter(user=self.request.user, revoked_at__isnull=True)


class AuthSessionRevokeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        session = AuthSession.objects.filter(id=session_id, user=request.user, revoked_at__isnull=True).first()
        if not session:
            return Response({'detail': '会话不存在。'}, status=status.HTTP_404_NOT_FOUND)
        outstanding = OutstandingToken.objects.filter(user=request.user, jti=session.refresh_jti).first()
        if outstanding:
            BlacklistedToken.objects.get_or_create(token=outstanding)
        session.revoked_at = timezone.now()
        session.save(update_fields=['revoked_at'])
        return Response({'detail': '会话已撤销。'})


class LogoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_value = str(request.data.get('refresh') or '')
        all_sessions = bool(request.data.get('all_sessions'))
        if all_sessions:
            for token in OutstandingToken.objects.filter(user=request.user):
                BlacklistedToken.objects.get_or_create(token=token)
            AuthSession.objects.filter(user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
            return Response({'detail': '所有设备已退出。'})
        if not refresh_value:
            return Response({'detail': '请提供 refresh token。'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_value)
            token.blacklist()
            AuthSession.objects.filter(user=request.user, refresh_jti=str(token['jti']), revoked_at__isnull=True).update(revoked_at=timezone.now())
        except TokenError:
            return Response({'detail': 'refresh token 无效。'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': '已退出。'})


def _export_user_data(user):
    payload = {
        'profile': UserProfileSerializer(user).data,
        'career_facts': list(user.career_facts.values()),
        'job_targets': list(user.job_targets.values()),
        'job_applications': list(user.job_applications.values()),
        'resumes': [
            {
                'id': resume.id,
                'title': resume.title,
                'status': resume.status,
                'current_version': resume.current_version.resume_json if resume.current_version else None,
            }
            for resume in user.resumes.select_related('current_version')
        ],
        'interview_sessions': list(user.interview_sessions.values('id', 'job_position', 'status', 'created_at', 'finished_at')),
        'generated_at': timezone.now().isoformat(),
    }
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


class PrivacyRequestView(generics.ListCreateAPIView):
    serializer_class = PrivacyRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PrivacyRequest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        request_type = serializer.validated_data['request_type']
        if request_type == PrivacyRequest.RequestType.EXPORT:
            serializer.save(
                user=self.request.user,
                status=PrivacyRequest.Status.COMPLETED,
                result=_export_user_data(self.request.user),
                completed_at=timezone.now(),
            )
        else:
            serializer.save(user=self.request.user)


class MFAStatusView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from allauth.mfa.models import Authenticator
        authenticators = set(Authenticator.objects.filter(user=request.user).values_list('type', flat=True))
        return Response({
            'enabled': Authenticator.Type.TOTP in authenticators,
            'recovery_codes_enabled': Authenticator.Type.RECOVERY_CODES in authenticators,
            'passkey_count': Authenticator.objects.filter(user=request.user, type=Authenticator.Type.WEBAUTHN).count(),
            'required': request.user.role in (User.Role.HR, User.Role.ADMIN) or request.user.is_staff,
        })


class MFASetupView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        import qrcode
        from allauth.mfa.models import Authenticator
        from allauth.mfa.totp.internal.auth import generate_totp_secret
        if Authenticator.objects.filter(user=request.user, type=Authenticator.Type.TOTP).exists():
            return Response({'detail': 'TOTP 已启用。'}, status=status.HTTP_409_CONFLICT)
        secret = generate_totp_secret()
        cache.set(f'mfa_setup:{request.user.id}', secret, timeout=600)
        issuer = 'iFaceoff'
        uri = f'otpauth://totp/{quote(issuer)}:{quote(request.user.email)}?secret={secret}&issuer={quote(issuer)}'
        image = qrcode.make(uri)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return Response({'secret': secret, 'otpauth_uri': uri, 'qr_code': f'data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode("ascii")}', 'expires_in': 600})


class MFAVerifyView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
        from allauth.mfa.totp.internal.auth import TOTP, validate_totp_code
        code = str(request.data.get('code') or '').strip()
        secret = cache.get(f'mfa_setup:{request.user.id}')
        if not secret:
            return Response({'detail': '设置会话已过期，请重新生成二维码。'}, status=status.HTTP_400_BAD_REQUEST)
        if not validate_totp_code(secret, code):
            return Response({'detail': '验证码不正确。'}, status=status.HTTP_400_BAD_REQUEST)
        TOTP.activate(request.user, secret)
        recovery = RecoveryCodes.activate(request.user)
        cache.delete(f'mfa_setup:{request.user.id}')
        return Response({'enabled': True, 'recovery_codes': recovery.get_unused_codes()})


class MFADisableView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from allauth.mfa.models import Authenticator
        password = str(request.data.get('password') or '')
        code = str(request.data.get('code') or '').strip()
        if not request.user.check_password(password):
            return Response({'detail': '密码不正确。'}, status=status.HTTP_400_BAD_REQUEST)
        totp = Authenticator.objects.filter(user=request.user, type=Authenticator.Type.TOTP).first()
        if not totp or not totp.wrap().validate_code(code):
            return Response({'detail': '双重验证代码不正确。'}, status=status.HTTP_400_BAD_REQUEST)
        Authenticator.objects.filter(user=request.user, type__in=[Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES]).delete()
        return Response({'enabled': False})
