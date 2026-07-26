from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from allauth.socialaccount.models import SocialAccount
from .models import AuthSession, NotificationPreference, PrivacyRequest, User
from .services import verify_email_code


# 【新增】为 SocialAccount 创建一个序列化器
class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ('id', 'provider', 'uid', 'last_login', 'date_joined', 'extra_data')


class UserProfileSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()
    mfa_enabled = serializers.SerializerMethodField()
    mfa_required = serializers.SerializerMethodField()
    # 【核心修正】确保 socialaccount_set 被正确声明
    socialaccount_set = SocialAccountSerializer(many=True, read_only=True)

    class Meta:
        model = User
        # 【核心修正】在 fields 列表中明确包含 socialaccount_set
        fields = (
            'id', 'username', 'email', 'phone', 'avatar', 'role', 'date_joined',
            'has_password', 'socialaccount_set', 'headline', 'location', 'years_experience',
            'target_roles', 'skills_profile', 'availability', 'profile_visibility',
            'onboarding_step', 'onboarding_completed_at',
            'mfa_enabled', 'mfa_required',
        )
        read_only_fields = ('email', 'role', 'date_joined', 'onboarding_completed_at', 'mfa_enabled', 'mfa_required')

    def get_has_password(self, obj):
        return obj.has_usable_password()

    def get_mfa_enabled(self, obj):
        try:
            from allauth.mfa.models import Authenticator
            return Authenticator.objects.filter(user=obj).exists()
        except (ImportError, RuntimeError):
            return False

    def get_mfa_required(self, obj):
        return obj.role in (User.Role.HR, User.Role.ADMIN) or obj.is_staff or obj.is_superuser


# --- 其他序列化器 (UserRegisterSerializer, PasswordChangeSerializer) 保持不变 ---
class UserRegisterSerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=6, min_length=6, write_only=True, required=True, help_text="邮箱验证码")
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'code')
        read_only_fields = ('id',)

    def validate(self, data):
        email = data.get('email')
        code = data.get('code')
        result = verify_email_code(email, code)
        if result == 'expired':
            raise serializers.ValidationError({"code": "验证码已过期或不存在，请重新发送。"})
        if result == 'locked':
            raise serializers.ValidationError({"code": "验证码错误次数过多，请重新发送。"})
        if result != 'ok':
            raise serializers.ValidationError({"code": "验证码错误。"})
        return data

    def create(self, validated_data):
        validated_data.pop('code')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=False, allow_blank=True, style={'input_type': 'password'})
    new_password1 = serializers.CharField(required=True, min_length=6, style={'input_type': 'password'},
                                          write_only=True)
    new_password2 = serializers.CharField(required=True, min_length=6, style={'input_type': 'password'},
                                          write_only=True)

    def validate(self, data):
        if data['new_password1'] != data['new_password2']:
            raise serializers.ValidationError({"new_password2": "两次输入的密码不一致。"})
        user = self.context['request'].user
        if user.has_usable_password():
            if not data.get('old_password'):
                raise serializers.ValidationError({"old_password": "请输入您的当前密码。"})
            if not user.check_password(data.get('old_password')):
                raise serializers.ValidationError({"old_password": "当前密码不正确。"})
        try:
            validate_password(data['new_password1'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password1': list(exc.messages)})
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        new_password = self.validated_data['new_password1']
        user.set_password(new_password)
        user.save()
        return user


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        exclude = ('user',)
        read_only_fields = ('updated_at',)


class AuthSessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = AuthSession
        fields = ['id', 'ip_address', 'user_agent', 'device_name', 'expires_at', 'last_seen_at', 'revoked_at', 'created_at', 'is_current']
        read_only_fields = fields

    def get_is_current(self, obj):
        return str(self.context.get('current_jti') or '') == obj.refresh_jti


class PrivacyRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacyRequest
        fields = ['id', 'request_type', 'status', 'result', 'reason', 'created_at', 'completed_at']
        read_only_fields = ('status', 'result', 'created_at', 'completed_at')
