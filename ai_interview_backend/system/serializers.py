# system/serializers.py
from rest_framework import serializers
from .models import AISetting, JobPosition, Industry  # 导入

class AISettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AISetting
        fields = ['ai_model', 'api_key']
        # 将 user 字段排除，因为它总是当前登录用户

class JobPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosition
        fields = ('id', 'name', 'description', 'icon_svg')

# 新增：用于行业列表的序列化器
class IndustryWithJobsSerializer(serializers.ModelSerializer):
    # 嵌套序列化器，会自动获取所有关联的 job_positions
    job_positions = JobPositionSerializer(many=True, read_only=True)

    class Meta:
        model = Industry
        fields = ('id', 'name', 'description', 'job_positions')