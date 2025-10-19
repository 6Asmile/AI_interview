# system/serializers.py
from rest_framework import serializers
from .models import AISetting, JobPosition, Industry, AIModel  # 导入

# 新增：用于 AI 模型列表
class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ('id', 'name', 'model_slug', 'description')

class AISettingSerializer(serializers.ModelSerializer):
    # 'ai_model_id' 用于接收用户选择的“默认模型”ID
    ai_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True),
        source='ai_model',
        write_only=True,
        allow_null=True,
        required=False # 设为非必须，因为用户可能只想更新 keys
    )
    # 'ai_model' 用于在返回数据时，嵌套展示默认模型的详细信息
    ai_model = AIModelSerializer(read_only=True)

    # 'api_keys' 字段现在是可读写的
    api_keys = serializers.JSONField(required=False)

    class Meta:
        model = AISetting
        fields = ['ai_model', 'ai_model_id', 'api_keys']
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