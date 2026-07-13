# system/serializers.py
from rest_framework import serializers
from .models import (
    AISetting,
    JobPosition,
    Industry,
    AIModel,
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ProviderCredential,
    RoutePolicy,
    RoutePolicyTarget,
    UsageBudget,
)
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
        legacy_keys = dict(instance.api_keys or {})
        instance = super().update(instance, validated_data)
        if incoming_keys is not None:
            user = self.context.get('request').user if self.context.get('request') else instance.user
            for key, value in (incoming_keys or {}).items():
                key = str(key)
                value = '' if value is None else str(value).strip()
                model = AIModel.objects.filter(id=key).first() or AIModel.objects.filter(model_slug=key).first()
                if not model:
                    raise serializers.ValidationError({'api_keys': f'模型 {key} 不存在。'})
                credential = ProviderCredential.objects.filter(
                    user=user,
                    legacy_model=model,
                    scope=ProviderCredential.Scope.BYOK,
                ).order_by('-updated_at').first()
                if not value:
                    if credential:
                        credential.delete()
                elif is_masked_api_key(value):
                    legacy_secret = str(legacy_keys.get(key) or '')
                    if not credential and legacy_secret and value == mask_api_key(legacy_secret):
                        credential = ProviderCredential(
                            user=user,
                            legacy_model=model,
                            name=f'{model.name} BYOK',
                            provider=model.provider,
                            scope=ProviderCredential.Scope.BYOK,
                        )
                        credential.set_secret(legacy_secret)
                        credential.full_clean()
                        credential.save()
                    elif not credential:
                        raise serializers.ValidationError(
                            {'api_keys': f'模型 {key} 的掩码密钥无法匹配现有凭据，请重新输入完整密钥。'}
                        )
                else:
                    credential = credential or ProviderCredential(
                        user=user,
                        legacy_model=model,
                        name=f'{model.name} BYOK',
                        provider=model.provider,
                        scope=ProviderCredential.Scope.BYOK,
                    )
                    credential.set_secret(value)
                    credential.full_clean()
                    credential.save()
                legacy_keys.pop(key, None)
            instance.api_keys = legacy_keys
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
            str(model_ref): mask_api_key(raw_secret)
            for model_ref, raw_secret in (instance.api_keys or {}).items()
            if raw_secret
        }
        data['api_keys'].update({
            str(item.legacy_model_id): item.secret_hint
            for item in ProviderCredential.objects.filter(
                user=instance.user,
                legacy_model__isnull=False,
                scope=ProviderCredential.Scope.BYOK,
                is_active=True,
            )
        })
        return data


class ProviderCredentialSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=True)

    class Meta:
        model = ProviderCredential
        fields = [
            'id', 'name', 'provider', 'scope', 'legacy_model', 'secret', 'secret_hint',
            'is_active', 'last_verified_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ('secret_hint', 'last_verified_at', 'created_at', 'updated_at')

    def validate_scope(self, value):
        user = self.context['request'].user
        if value == ProviderCredential.Scope.PLATFORM and not (user.is_staff or user.role == 'admin'):
            raise serializers.ValidationError('只有管理员可以管理平台凭据。')
        return value

    def create(self, validated_data):
        secret = validated_data.pop('secret', '')
        user = self.context['request'].user
        scope = validated_data.get('scope', ProviderCredential.Scope.BYOK)
        credential = ProviderCredential(
            user=None if scope == ProviderCredential.Scope.PLATFORM else user,
            **validated_data,
        )
        if not secret:
            raise serializers.ValidationError({'secret': '请输入密钥。'})
        credential.set_secret(secret)
        credential.full_clean()
        credential.save()
        return credential

    def update(self, instance, validated_data):
        secret = validated_data.pop('secret', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if secret and not is_masked_api_key(secret):
            instance.set_secret(secret)
        instance.full_clean()
        instance.save()
        return instance


class ModelDeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelDeployment
        fields = '__all__'
        read_only_fields = ('last_health_status', 'last_health_at', 'created_at', 'updated_at')


class RoutePolicyTargetSerializer(serializers.ModelSerializer):
    deployment_detail = ModelDeploymentSerializer(source='deployment', read_only=True)

    class Meta:
        model = RoutePolicyTarget
        fields = ['id', 'policy', 'deployment', 'deployment_detail', 'order', 'weight', 'retry_count', 'is_active']


class RoutePolicySerializer(serializers.ModelSerializer):
    targets = RoutePolicyTargetSerializer(many=True, read_only=True)

    class Meta:
        model = RoutePolicy
        fields = ['id', 'alias', 'strategy', 'total_timeout_seconds', 'max_attempts', 'is_active', 'targets', 'created_at', 'updated_at']
        read_only_fields = ('created_at', 'updated_at')


class ModelAliasSerializer(serializers.ModelSerializer):
    route_policy = RoutePolicySerializer(read_only=True)

    class Meta:
        model = ModelAlias
        fields = ['id', 'slug', 'name', 'model_type', 'description', 'is_active', 'route_policy', 'created_at', 'updated_at']
        read_only_fields = ('created_at', 'updated_at')


class UsageBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageBudget
        fields = '__all__'
        read_only_fields = ('used_input_tokens', 'used_output_tokens', 'used_cost', 'updated_at')


class ModelRequestLedgerSerializer(serializers.ModelSerializer):
    alias_slug = serializers.CharField(source='alias.slug', read_only=True)
    deployment_name = serializers.CharField(source='deployment.name', read_only=True)

    class Meta:
        model = ModelRequestLedger
        fields = [
            'request_id', 'task_name', 'status', 'alias_slug', 'deployment_name',
            'input_tokens', 'output_tokens', 'estimated_cost', 'latency_ms',
            'fallback_count', 'error_code', 'metadata', 'created_at', 'completed_at',
        ]
        read_only_fields = fields
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
