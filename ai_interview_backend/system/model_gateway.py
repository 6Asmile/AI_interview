import json
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests
from django.conf import settings
from openai import OpenAI

from .ai_config import resolve_ai_config
from .models import AIModel
from .gateway_executor import GatewayBudgetExceeded, GatewayExecutionError, GatewayExecutor


class ModelGatewayError(RuntimeError):
    pass


@dataclass
class GatewayConfig:
    api_key: str | None
    model: AIModel | None
    source: str

    @property
    def provider(self) -> str:
        return (self.model.provider if self.model else '') or ''

    @property
    def model_slug(self) -> str:
        return (self.model.model_slug if self.model else '') or ''

    @property
    def base_url(self) -> str:
        return (self.model.base_url if self.model else '') or ''

    def snapshot(self, include_key: bool = False) -> dict[str, Any]:
        data = {
            'provider': self.provider,
            'model_slug': self.model_slug,
            'model_type': self.model.model_type if self.model else '',
            'base_url': self.base_url,
            'key_source': self.source,
            'has_api_key': bool(self.api_key),
        }
        if include_key:
            data['api_key'] = self.api_key
        else:
            data['api_key_masked'] = mask_api_key(self.api_key)
        return data


def mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return ''
    if len(api_key) <= 12:
        return '*' * len(api_key)
    return f'{api_key[:6]}...{api_key[-4:]}'


def is_masked_api_key(value: str | None) -> bool:
    value = (value or '').strip()
    return bool(value) and ('*' in value or '...' in value)


def resolve_gateway_config(user=None, model_type: str = AIModel.ModelType.CHAT) -> GatewayConfig:
    resolved = resolve_ai_config(user, model_type)
    return GatewayConfig(api_key=resolved.api_key, model=resolved.model, source=resolved.source)


class ModelGateway:
    """Centralized provider gateway for chat, embedding and rerank model calls.

    The gateway keeps online code independent from provider-specific endpoint
    details. It is intentionally thin: provider routing, fallback and health
    status live here; interview/knowledge logic only consumes typed methods.
    """

    def __init__(self, user=None, timeout: int | None = None):
        self.user = user
        self.timeout = int(timeout or getattr(settings, 'MODEL_GATEWAY_TIMEOUT_SECONDS', 30))
        self.executor = GatewayExecutor(user)

    def _use_alias(self, alias_slug: str, callback):
        return callback(self.executor, alias_slug)

    def config(self, model_type: str) -> GatewayConfig:
        return resolve_gateway_config(self.user, model_type)

    def _require(self, model_type: str) -> GatewayConfig:
        config = self.config(model_type)
        if not config.model:
            raise ModelGatewayError(f'{model_type}_model_missing')
        if not config.api_key:
            raise ModelGatewayError(f'{model_type}_api_key_missing')
        return config

    def _openai_client(self, config: GatewayConfig) -> OpenAI:
        return OpenAI(api_key=config.api_key, base_url=config.base_url or None)

    def chat_json(self, messages: list[dict], *, max_tokens: int = 1024, temperature: float = 0.3, alias_slug: str = 'chat.default') -> dict:
        routed = self._use_alias(alias_slug, lambda executor, alias: executor.chat_json(alias, messages, task_name=alias, max_tokens=max_tokens, temperature=temperature))
        if routed is not None:
            return routed
        config = self._require(AIModel.ModelType.CHAT)
        client = self._openai_client(config)
        params = {
            'model': config.model_slug,
            'messages': messages,
            'stream': False,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if config.model and config.model.supports_json_mode:
            params['response_format'] = {'type': 'json_object'}
        response = client.chat.completions.create(**params)
        content = response.choices[0].message.content or '{}'
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        return json.loads(content.strip() or '{}')

    def chat_stream(self, messages: list[dict], *, max_tokens: int = 1024, temperature: float = 0.7, alias_slug: str = 'chat.default'):
        yield from self.executor.chat_stream(
            alias_slug,
            messages,
            task_name=alias_slug,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def embed_text(self, text: str, alias_slug: str = 'embedding.default') -> tuple[list[float] | None, str, dict]:
        routed = self._use_alias(alias_slug, lambda executor, alias: executor.embed_text(alias, text, task_name=alias))
        if routed is not None:
            return routed
        config = self._require(AIModel.ModelType.EMBEDDING)
        client = self._openai_client(config)
        response = client.embeddings.create(model=config.model_slug, input=(text or '')[:8000])
        vector = response.data[0].embedding
        return vector, config.model_slug, config.snapshot()

    def _rerank_url(self, config: GatewayConfig) -> str:
        base_url = config.base_url.rstrip('/')
        if '/services/rerank/' in base_url:
            return base_url
        if base_url.endswith('/api/v1'):
            return f'{base_url}/services/rerank/text-rerank/text-rerank'
        if 'compatible-mode' in base_url:
            return base_url.replace('/compatible-mode/v1', '/api/v1/services/rerank/text-rerank/text-rerank')
        return base_url

    def rerank(self, query: str, documents: Iterable[str], *, top_n: int = 4, alias_slug: str = 'rerank.default') -> tuple[list[dict], dict]:
        docs = [str(item or '') for item in documents]
        routed = self._use_alias(alias_slug, lambda executor, alias: executor.rerank(alias, query, docs, top_n=top_n, task_name=alias))
        if routed is not None:
            return routed
        config = self._require(AIModel.ModelType.RERANK)
        if not docs:
            return [], config.snapshot()
        url = self._rerank_url(config)
        safe_top_n = min(max(int(top_n or len(docs)), 1), len(docs))
        if 'aliyun' in config.provider or 'dashscope' in config.provider or '/api/v1/services/rerank/' in url:
            payload = {
                'model': config.model_slug,
                'input': {
                    'query': query,
                    'documents': docs,
                },
                'parameters': {
                    'top_n': safe_top_n,
                    'return_documents': False,
                },
            }
        else:
            payload = {
                'model': config.model_slug,
                'query': query,
                'documents': docs,
                'top_n': safe_top_n,
                'return_documents': False,
            }
        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'},
            timeout=self.timeout,
        )
        if not response.ok:
            raise ModelGatewayError(f'rerank_http_{response.status_code}: {response.text[:500]}')
        data = response.json()
        results = data.get('results') or data.get('output', {}).get('results') or []
        return results, {**config.snapshot(), 'endpoint': url}

    def health_check(self, model_type: str) -> dict[str, Any]:
        started = time.perf_counter()
        config = self.config(model_type)
        result = {
            'ok': False,
            'model_type': model_type,
            'config': config.snapshot(),
            'latency_ms': None,
            'error': '',
        }
        try:
            if model_type == AIModel.ModelType.CHAT:
                data = self.chat_json(
                    [{'role': 'user', 'content': 'Return JSON only: {"ok": true}'}],
                    max_tokens=32,
                    temperature=0,
                )
                result['ok'] = bool(data)
            elif model_type == AIModel.ModelType.EMBEDDING:
                vector, model_slug, _ = self.embed_text('health check')
                result['ok'] = bool(vector)
                result['dimension'] = len(vector or [])
                result['model_slug'] = model_slug
            elif model_type == AIModel.ModelType.RERANK:
                results, _ = self.rerank('health check', ['health check document', 'irrelevant'], top_n=1)
                result['ok'] = bool(results)
            else:
                if not config.model:
                    raise ModelGatewayError(f'{model_type}_model_missing')
                if not config.api_key:
                    raise ModelGatewayError(f'{model_type}_api_key_missing')
                result['ok'] = True
                result['note'] = 'configured_only'
        except Exception as exc:
            if (
                isinstance(exc, GatewayExecutionError) and
                str(exc).startswith(('alias_not_configured:', 'no_available_deployment:')) and
                config.model and not config.api_key
            ):
                result['error'] = f'{model_type}_api_key_missing'
            else:
                result['error'] = str(exc)[:500]
        finally:
            result['latency_ms'] = int((time.perf_counter() - started) * 1000)
        return result


def gateway_env_defaults() -> dict[str, str]:
    return {
        'MODEL_GATEWAY_TIMEOUT_SECONDS': str(getattr(settings, 'MODEL_GATEWAY_TIMEOUT_SECONDS', 30)),
        'MODEL_GATEWAY_FALLBACK_ENABLED': os.getenv('MODEL_GATEWAY_FALLBACK_ENABLED', 'true'),
    }
