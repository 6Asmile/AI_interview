import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openai import OpenAI

from .models import (
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ProviderCredential,
    UsageBudget,
)


class GatewayExecutionError(RuntimeError):
    pass


class GatewayBudgetExceeded(GatewayExecutionError):
    pass


@dataclass
class ExecutionTarget:
    alias: ModelAlias
    deployment: ModelDeployment
    api_key: str
    timeout: int


def _month_start():
    today = timezone.localdate()
    return today.replace(day=1)


def _estimate_tokens(value) -> int:
    if isinstance(value, list):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value or '')
    return max(1, len(text) // 4)


class GatewayExecutor:
    """Task-oriented model gateway with routing, BYOK isolation and metering."""

    def __init__(self, user=None):
        self.user = user if getattr(user, 'is_authenticated', False) else None

    def _budget(self):
        if not self.user:
            return None
        budget = UsageBudget.objects.filter(user=self.user, is_active=True).first()
        if not budget:
            return None
        current = _month_start()
        if budget.period_start != current:
            budget.period_start = current
            budget.used_input_tokens = 0
            budget.used_output_tokens = 0
            budget.used_cost = Decimal('0')
            budget.save(update_fields=['period_start', 'used_input_tokens', 'used_output_tokens', 'used_cost', 'updated_at'])
        if budget.monthly_token_limit and budget.used_input_tokens + budget.used_output_tokens >= budget.monthly_token_limit:
            raise GatewayBudgetExceeded('monthly_token_budget_exceeded')
        if budget.monthly_cost_limit and budget.used_cost >= budget.monthly_cost_limit:
            raise GatewayBudgetExceeded('monthly_cost_budget_exceeded')
        return budget

    def _credential_for(self, deployment: ModelDeployment) -> str:
        if self.user:
            user_credential = ProviderCredential.objects.filter(
                Q(legacy_model__model_slug=deployment.remote_model) | Q(legacy_model__isnull=True),
                user=self.user,
                provider=deployment.provider,
                scope=ProviderCredential.Scope.BYOK,
                is_active=True,
            ).order_by('-legacy_model_id', '-updated_at').first()
            if user_credential:
                return user_credential.get_secret()
        credential = deployment.credential
        if credential and credential.is_active:
            if credential.scope == ProviderCredential.Scope.BYOK and credential.user_id != getattr(self.user, 'id', None):
                raise GatewayExecutionError('credential_tenant_mismatch')
            return credential.get_secret()
        raise GatewayExecutionError('deployment_credential_missing')

    def targets(self, alias_slug: str) -> list[ExecutionTarget]:
        try:
            alias = ModelAlias.objects.select_related('route_policy').get(slug=alias_slug, is_active=True)
        except ModelAlias.DoesNotExist as exc:
            raise GatewayExecutionError(f'alias_not_configured:{alias_slug}') from exc
        policy = getattr(alias, 'route_policy', None)
        if not policy or not policy.is_active:
            raise GatewayExecutionError(f'route_policy_not_configured:{alias_slug}')
        targets = policy.targets.filter(is_active=True, deployment__is_active=True).select_related('deployment', 'deployment__credential')
        resolved = []
        for target in targets[:max(1, policy.max_attempts)]:
            try:
                key = self._credential_for(target.deployment)
            except (GatewayExecutionError, ValueError):
                continue
            resolved.append(ExecutionTarget(
                alias=alias,
                deployment=target.deployment,
                api_key=key,
                timeout=min(target.deployment.timeout_seconds, policy.total_timeout_seconds),
            ))
        if not resolved:
            raise GatewayExecutionError(f'no_available_deployment:{alias_slug}')
        return resolved

    def _ledger(self, alias, task_name, input_summary) -> ModelRequestLedger:
        try:
            self._budget()
        except GatewayBudgetExceeded as exc:
            ModelRequestLedger.objects.create(
                user=self.user,
                alias=alias,
                task_name=task_name,
                status=ModelRequestLedger.Status.REJECTED,
                error_code=str(exc),
                metadata={'input_units': _estimate_tokens(input_summary)},
                completed_at=timezone.now(),
            )
            raise
        return ModelRequestLedger.objects.create(
            user=self.user,
            alias=alias,
            task_name=task_name,
            metadata={'input_units': _estimate_tokens(input_summary)},
        )

    @transaction.atomic
    def _complete(self, ledger, target, *, started, input_tokens, output_tokens, success, error='', fallback_count=0):
        input_cost = Decimal(input_tokens) * target.deployment.input_price_per_million / Decimal(1_000_000)
        output_cost = Decimal(output_tokens) * target.deployment.output_price_per_million / Decimal(1_000_000)
        cost = input_cost + output_cost
        ledger.deployment = target.deployment
        ledger.status = ModelRequestLedger.Status.SUCCEEDED if success else ModelRequestLedger.Status.FAILED
        ledger.input_tokens = max(0, input_tokens)
        ledger.output_tokens = max(0, output_tokens)
        ledger.estimated_cost = cost
        ledger.latency_ms = int((time.perf_counter() - started) * 1000)
        ledger.fallback_count = fallback_count
        ledger.error_code = str(error)[:120]
        ledger.completed_at = timezone.now()
        ledger.save()
        if success and self.user:
            budget = UsageBudget.objects.select_for_update().filter(user=self.user, is_active=True).first()
            if budget:
                budget.used_input_tokens += max(0, input_tokens)
                budget.used_output_tokens += max(0, output_tokens)
                budget.used_cost += cost
                budget.save(update_fields=['used_input_tokens', 'used_output_tokens', 'used_cost', 'updated_at'])
        target.deployment.last_health_status = 'healthy' if success else 'degraded'
        target.deployment.last_health_at = timezone.now()
        target.deployment.save(update_fields=['last_health_status', 'last_health_at', 'updated_at'])

    def chat_json(self, alias_slug: str, messages: list[dict], *, task_name: str | None = None, max_tokens=1024, temperature=0.3) -> dict:
        targets = self.targets(alias_slug)
        ledger = self._ledger(targets[0].alias, task_name or alias_slug, messages)
        started = time.perf_counter()
        last_error = ''
        for index, target in enumerate(targets):
            try:
                response = OpenAI(api_key=target.api_key, base_url=target.deployment.base_url or None, timeout=target.timeout).chat.completions.create(
                    model=target.deployment.remote_model,
                    messages=messages,
                    stream=False,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={'type': 'json_object'},
                )
                content = (response.choices[0].message.content or '{}').strip()
                if content.startswith('```json'):
                    content = content[7:]
                if content.endswith('```'):
                    content = content[:-3]
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) or _estimate_tokens(messages)
                output_tokens = getattr(usage, 'completion_tokens', 0) or _estimate_tokens(content)
                result = json.loads(content.strip() or '{}')
                self._complete(ledger, target, started=started, input_tokens=input_tokens, output_tokens=output_tokens, success=True, fallback_count=index)
                return result
            except Exception as exc:
                last_error = type(exc).__name__
        self._complete(ledger, targets[-1], started=started, input_tokens=_estimate_tokens(messages), output_tokens=0, success=False, error=last_error, fallback_count=max(0, len(targets) - 1))
        raise GatewayExecutionError(last_error or 'chat_json_failed')

    def chat_stream(self, alias_slug: str, messages: list[dict], *, task_name: str | None = None, max_tokens=1024, temperature=0.7):
        targets = self.targets(alias_slug)
        ledger = self._ledger(targets[0].alias, task_name or alias_slug, messages)
        started = time.perf_counter()
        last_error = ''
        for index, target in enumerate(targets):
            chunks = []
            try:
                stream = OpenAI(api_key=target.api_key, base_url=target.deployment.base_url or None, timeout=target.timeout).chat.completions.create(
                    model=target.deployment.remote_model,
                    messages=messages,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                for chunk in stream:
                    value = chunk.choices[0].delta.content or ''
                    chunks.append(value)
                    yield value
                self._complete(
                    ledger,
                    target,
                    started=started,
                    input_tokens=_estimate_tokens(messages),
                    output_tokens=_estimate_tokens(''.join(chunks)),
                    success=True,
                    fallback_count=index,
                )
                return
            except Exception as exc:
                # Once output has reached the client it is unsafe to retry on another model.
                last_error = type(exc).__name__
                if chunks:
                    self._complete(ledger, target, started=started, input_tokens=_estimate_tokens(messages), output_tokens=_estimate_tokens(''.join(chunks)), success=False, error=last_error, fallback_count=index)
                    raise GatewayExecutionError(last_error) from exc
        self._complete(ledger, targets[-1], started=started, input_tokens=_estimate_tokens(messages), output_tokens=0, success=False, error=last_error, fallback_count=max(0, len(targets) - 1))
        raise GatewayExecutionError(last_error or 'chat_stream_failed')

    def embed_text(self, alias_slug: str, text: str, *, task_name: str | None = None):
        targets = self.targets(alias_slug)
        ledger = self._ledger(targets[0].alias, task_name or alias_slug, text)
        started = time.perf_counter()
        last_error = ''
        for index, target in enumerate(targets):
            try:
                response = OpenAI(api_key=target.api_key, base_url=target.deployment.base_url or None, timeout=target.timeout).embeddings.create(
                    model=target.deployment.remote_model,
                    input=(text or '')[:16000],
                )
                vector = response.data[0].embedding
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) or _estimate_tokens(text)
                self._complete(ledger, target, started=started, input_tokens=input_tokens, output_tokens=0, success=True, fallback_count=index)
                return vector, target.deployment.remote_model, {'alias': alias_slug, 'deployment': target.deployment.name}
            except Exception as exc:
                last_error = type(exc).__name__
        self._complete(ledger, targets[-1], started=started, input_tokens=_estimate_tokens(text), output_tokens=0, success=False, error=last_error, fallback_count=max(0, len(targets) - 1))
        raise GatewayExecutionError(last_error or 'embedding_failed')

    def rerank(self, alias_slug: str, query: str, documents: Iterable[str], *, top_n=4, task_name: str | None = None):
        docs = [str(item or '') for item in documents]
        targets = self.targets(alias_slug)
        ledger = self._ledger(targets[0].alias, task_name or alias_slug, [query, *docs])
        started = time.perf_counter()
        last_error = ''
        for index, target in enumerate(targets):
            try:
                url = target.deployment.base_url.rstrip('/')
                payload = {'model': target.deployment.remote_model, 'query': query, 'documents': docs, 'top_n': min(max(1, top_n), len(docs)), 'return_documents': False}
                response = requests.post(url, json=payload, headers={'Authorization': f'Bearer {target.api_key}'}, timeout=target.timeout)
                response.raise_for_status()
                data = response.json()
                results = data.get('results') or data.get('output', {}).get('results') or []
                self._complete(ledger, target, started=started, input_tokens=_estimate_tokens([query, *docs]), output_tokens=0, success=True, fallback_count=index)
                return results, {'alias': alias_slug, 'deployment': target.deployment.name}
            except Exception as exc:
                last_error = type(exc).__name__
        self._complete(ledger, targets[-1], started=started, input_tokens=_estimate_tokens([query, *docs]), output_tokens=0, success=False, error=last_error, fallback_count=max(0, len(targets) - 1))
        raise GatewayExecutionError(last_error or 'rerank_failed')
