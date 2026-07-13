# system/serializers.py
from rest_framework import serializers
from .models import AISetting, JobPosition, Industry, AIModel  # 导入
from .model_gateway import is_masked_api_key, mask_api_key

# 新增：用于 AI 模型列表
class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ('id', 'name', 'model_slug', 'base_url', 'provider', 'model_type', 'description', 'supports_json_mode', 'dimension')

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
    chat_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True, model_type=AIModel.ModelType.CHAT),
        source='chat_model',
        write_only=True,
        allow_null=True,
        required=False
    )
    embedding_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True, model_type=AIModel.ModelType.EMBEDDING),
        source='embedding_model',
        write_only=True,
        allow_null=True,
        required=False
    )
    rerank_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True, model_type=AIModel.ModelType.RERANK),
        source='rerank_model',
        write_only=True,
        allow_null=True,
        required=False
    )
    asr_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True, model_type=AIModel.ModelType.ASR),
        source='asr_model',
        write_only=True,
        allow_null=True,
        required=False
    )
    tts_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AIModel.objects.filter(is_active=True, model_type=AIModel.ModelType.TTS),
        source='tts_model',
        write_only=True,
        allow_null=True,
        required=False
    )
    chat_model = AIModelSerializer(read_only=True)
    embedding_model = AIModelSerializer(read_only=True)
    rerank_model = AIModelSerializer(read_only=True)
    asr_model = AIModelSerializer(read_only=True)
    tts_model = AIModelSerializer(read_only=True)

    # 'api_keys' 字段现在是可读写的
    api_keys = serializers.JSONField(required=False)

    class Meta:
        model = AISetting
        fields = [
            'ai_model',
            'ai_model_id',
            'chat_model',
            'chat_model_id',
            'embedding_model',
            'embedding_model_id',
            'rerank_model',
            'rerank_model_id',
            'asr_model',
            'asr_model_id',
            'tts_model',
            'tts_model_id',
            'api_keys',
        ]

    def update(self, instance, validated_data):
        incoming_keys = validated_data.pop('api_keys', None)
        instance = super().update(instance, validated_data)
        if incoming_keys is not None:
            merged_keys = dict(instance.api_keys or {})
            for key, value in (incoming_keys or {}).items():
                key = str(key)
                value = '' if value is None else str(value).strip()
                if not value:
                    merged_keys.pop(key, None)
                elif is_masked_api_key(value):
                    # The frontend sends masked values back unchanged; keep the stored secret.
                    continue
                else:
                    merged_keys[key] = value
            instance.api_keys = merged_keys
            instance.save(update_fields=['api_keys', 'updated_at'])
        if instance.chat_model and instance.ai_model_id != instance.chat_model_id:
            instance.ai_model = instance.chat_model
            instance.save(update_fields=['ai_model', 'updated_at'])
        elif instance.ai_model and not instance.chat_model:
            instance.chat_model = instance.ai_model
            instance.save(update_fields=['chat_model', 'updated_at'])
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['api_keys'] = {
            str(key): mask_api_key(value)
            for key, value in (instance.api_keys or {}).items()
            if value
        }
        return data
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
