# users/serializers.py
from rest_framework import serializers
from .models import User

class UserRegisterSerializer(serializers.ModelSerializer):
    # 确保密码在序列化输出时不被包含
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        # 定义序列化器包含的字段
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        """
        重写 create 方法以处理密码哈希
        """
        # 使用 Django 内置的 create_user 方法，它会自动处理密码哈希
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user