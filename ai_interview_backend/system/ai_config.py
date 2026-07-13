import os
from dataclasses import dataclass

from django.conf import settings

from .models import AIModel, AISetting, ProviderCredential


@dataclass
class ResolvedAIConfig:
    api_key: str | None
    model: AIModel | None
    source: str


DEFAULT_SLUGS = {
    AIModel.ModelType.CHAT: 'deepseek-chat',
    AIModel.ModelType.EMBEDDING: 'text-embedding-v3',
    AIModel.ModelType.RERANK: 'qwen-rerank',
    AIModel.ModelType.ASR: 'paraformer-realtime-v2',
    AIModel.ModelType.TTS: 'cosyvoice-v1',
}


def get_setting(user) -> AISetting | None:
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    try:
        return user.ai_setting
    except AISetting.DoesNotExist:
        return None


def resolve_ai_config(user=None, model_type: str = AIModel.ModelType.CHAT) -> ResolvedAIConfig:
    setting = get_setting(user)
    selected_model = None
    if setting:
        if model_type == AIModel.ModelType.CHAT:
            selected_model = setting.chat_model or setting.ai_model
        elif model_type == AIModel.ModelType.EMBEDDING:
            selected_model = setting.embedding_model
        elif model_type == AIModel.ModelType.RERANK:
            selected_model = setting.rerank_model
        elif model_type == AIModel.ModelType.ASR:
            selected_model = setting.asr_model
        elif model_type == AIModel.ModelType.TTS:
            selected_model = setting.tts_model

    if not selected_model:
        selected_model = AIModel.objects.filter(
            model_type=model_type,
            model_slug=DEFAULT_SLUGS.get(model_type, ''),
            is_active=True,
        ).first()
    if not selected_model and model_type == AIModel.ModelType.CHAT:
        selected_model = AIModel.objects.filter(model_slug='deepseek-chat', is_active=True).first()

    api_key = None
    source = 'missing'
    if selected_model and user and getattr(user, 'is_authenticated', False):
        credential = ProviderCredential.objects.filter(
            user=user,
            legacy_model=selected_model,
            scope=ProviderCredential.Scope.BYOK,
            is_active=True,
        ).order_by('-updated_at').first()
        if credential:
            try:
                api_key = credential.get_secret()
            except ValueError:
                api_key = None
            if api_key:
                source = 'user_encrypted'

    # Compatibility for installations that have not applied the credential migration yet.
    if not api_key and selected_model and setting and setting.api_keys:
        api_key = setting.api_keys.get(str(selected_model.id)) or setting.api_keys.get(selected_model.model_slug)
        if api_key:
            source = 'user_legacy'

    if not api_key:
        env_key = {
            AIModel.ModelType.CHAT: 'DEEPSEEK_API_KEY',
            AIModel.ModelType.EMBEDDING: 'DASHSCOPE_API_KEY',
            AIModel.ModelType.RERANK: 'DASHSCOPE_API_KEY',
            AIModel.ModelType.ASR: 'DASHSCOPE_API_KEY',
            AIModel.ModelType.TTS: 'DASHSCOPE_API_KEY',
        }.get(model_type)
        api_key = os.getenv(env_key or '') or getattr(settings, f'{model_type.upper()}_API_KEY', '')
        if api_key:
            source = 'system'

    return ResolvedAIConfig(api_key=api_key, model=selected_model, source=source)
