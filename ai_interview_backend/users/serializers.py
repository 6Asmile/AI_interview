# users/serializers.py
from rest_framework import serializers
from django.core.cache import cache
from .models import User


class UserRegisterSerializer(serializers.ModelSerializer):
    # 1. 明确添加 code 字段，并设置为只写 (write_only)
    #    这意味着它只用于输入验证，绝不会在API响应中返回
    code = serializers.CharField(max_length=6, min_length=6, write_only=True, required=True, help_text="邮箱验证码")

    # 确保密码字段也设置为只写
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        # 2. 在 fields 中包含 username, email, password, code
        fields = ('id', 'username', 'email', 'password', 'code')
        # id 是只读的，它会在创建后由数据库生成
        read_only_fields = ('id',)

    def validate(self, data):
        """
        3. 重写 validate 方法，进行跨字段的综合验证。
        """
        email = data.get('email')
        code = data.get('code')

        # 从 Redis 中获取该邮箱对应的验证码
        cache_key = f"email_code_{email}"
        cached_code = cache.get(cache_key)

        if not cached_code:
            raise serializers.ValidationError({"code": "验证码已过期或不存在，请重新发送。"})

        if cached_code.lower() != code.lower():
            raise serializers.ValidationError({"code": "验证码错误。"})

        # 验证通过后，可以删除这个 code，因为它不需要存入数据库
        # data.pop('code') # 我们将在 create 方法中处理它
        return data

    def create(self, validated_data):
        """
        重写 create 方法，创建用户并处理密码哈希。
        """
        # 4. 在创建用户前，将 'code' 字段从数据中移除
        validated_data.pop('code')

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )

        # 5. 注册成功后，为了防止验证码被重复使用，从 Redis 中删除它
        cache.delete(f"email_code_{validated_data['email']}")

        return user


class UserProfileSerializer(serializers.ModelSerializer):
    # 新增一个只读字段
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        # 在 fields 中加入 'has_password'
        fields = ('id', 'username', 'email', 'phone', 'avatar', 'role', 'date_joined', 'has_password')

    def get_has_password(self, obj):
        # 调用 Django User 模型的内置方法
        return obj.has_usable_password()


class PasswordChangeSerializer(serializers.Serializer):
    """
    用于处理用户修改密码的序列化器。
    """
    old_password = serializers.CharField(required=False, allow_blank=True, style={'input_type': 'password'})
    new_password1 = serializers.CharField(required=True, min_length=6, style={'input_type': 'password'},
                                          write_only=True)
    new_password2 = serializers.CharField(required=True, min_length=6, style={'input_type': 'password'},
                                          write_only=True)

    def validate(self, data):
        # 确认两次输入的新密码是否一致
        if data['new_password1'] != data['new_password2']:
            raise serializers.ValidationError({"new_password2": "两次输入的密码不一致。"})

        user = self.context['request'].user

        # 如果用户已有密码 (不是纯 OAuth 用户)，则必须验证旧密码
        if user.has_usable_password():
            if not data.get('old_password'):
                raise serializers.ValidationError({"old_password": "请输入您的当前密码。"})
            if not user.check_password(data.get('old_password')):
                raise serializers.ValidationError({"old_password": "当前密码不正确。"})

        # 如果用户没有密码 (纯 OAuth 用户)，则 old_password 字段会被忽略
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        new_password = self.validated_data['new_password1']
        user.set_password(new_password)
        user.save()
        return user