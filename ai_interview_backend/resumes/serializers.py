# resumes/serializers.py
from rest_framework import serializers
from .models import Resume
from users.serializers import UserRegisterSerializer  # 借用一下，只为了显示用户信息

class ResumeCreateSerializer(serializers.ModelSerializer):
    """
    一个专用于创建简历的序列化器。
    它只包含需要用户输入的字段。
    """
    class Meta:
        model = Resume
        # 我们只关心 'title'。'file' 将从 request.FILES 中单独处理。
        fields = ['title']
        # title 是可选的，如果用户不提供，我们会用文件名代替
        extra_kwargs = {
            'title': {'required': False, 'allow_blank': True}
        }


class ResumeSerializer(serializers.ModelSerializer):
    # 创建一个只读字段来显示关联的用户信息，避免循环导入
    # 这里我们只想显示用户名和邮箱，而不是完整的用户信息
    user_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Resume
        # fields = '__all__' # 包含所有字段
        # 为了安全和简洁，我们最好明确指定字段
        fields = [
            'id',
            'user',
            'user_info',
            'title',
            'file',
            'file_type',
            'file_size',
            'is_default',
            'status',
            'created_at',
            'updated_at'
        ]
        # 将 'user' 字段设置为只读，因为在创建时我们会从请求的用户中自动获取
        read_only_fields = ['user', 'user_info', 'status']

    def get_user_info(self, obj):
        # 'obj' 是当前的 Resume 实例
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }

    def create(self, validated_data):
        # 在创建简历时，将当前登录的用户自动关联
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)