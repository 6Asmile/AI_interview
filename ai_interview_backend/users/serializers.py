from rest_framework import serializers
from django.core.cache import cache
from allauth.socialaccount.models import SocialAccount
from .models import User


# 【新增】为 SocialAccount 创建一个序列化器
class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ('id', 'provider', 'uid', 'last_login', 'date_joined', 'extra_data')


class UserProfileSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()
    # 【核心修正】确保 socialaccount_set 被正确声明
    socialaccount_set = SocialAccountSerializer(many=True, read_only=True)

    class Meta:
        model = User
        # 【核心修正】在 fields 列表中明确包含 socialaccount_set
        fields = (
        'id', 'username', 'email', 'phone', 'avatar', 'role', 'date_joined', 'has_password', 'socialaccount_set')

    def get_has_password(self, obj):
        return obj.has_usable_password()


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
        cache_key = f"email_code_{email}"
        cached_code = cache.get(cache_key)
        if not cached_code:
            raise serializers.ValidationError({"code": "验证码已过期或不存在，请重新发送。"})
        if cached_code.lower() != code.lower():
            raise serializers.ValidationError({"code": "验证码错误。"})
        return data

    def create(self, validated_data):
        validated_data.pop('code')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        cache.delete(f"email_code_{validated_data['email']}")
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
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        new_password = self.validated_data['new_password1']
        user.set_password(new_password)
        user.save()
        return user