# system/serializers.py
from rest_framework import serializers
from .models import AISetting, JobPosition, Industry, AIModel  # 导入

# 新增：用于 AI 模型列表
class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ('id', 'name', 'model_slug', 'description')

class AISettingSerializer(serializers.ModelSerializer):
    # 【核心改造】使用 ai_model_id 来处理输入，使用嵌套序列化器来处理输出
    ai_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True),
        source='ai_model',
        write_only=True,
        allow_null=True
    )
    ai_model = AIModelSerializer(read_only=True)

    class Meta:
        model = AISetting
        fields = ['ai_model', 'ai_model_id', 'api_key']
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