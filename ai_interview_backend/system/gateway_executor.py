import json
import hashlib
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

import requests
from django_redis import get_redis_connection
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from openai import OpenAI

from core.admission import concurrency_lease
from core.redis_keys import build_redis_key

from .models import (
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ModelAttempt,
    ProviderCredential,
    UsageBudget,
)


class GatewayExecutionError(RuntimeError):
    pass


class GatewayBudgetExceeded(GatewayExecutionError):
    pass


class GatewayDeadlineExceeded(GatewayExecutionError):
    pass


class GatewayCircuitOpen(GatewayExecutionError):
    def __init__(self, retry_after_ms: int):
        self.retry_after_ms = max(1, int(retry_after_ms or 1))
        super().__init__('model_deployment_circuit_open')


class GatewayCoordinationUnavailable(GatewayExecutionError):
    pass


@dataclass
class ExecutionTarget:
    alias: ModelAlias
    deployment: ModelDeployment
    api_key: str
    timeout: int
    total_timeout: int


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    category: str
    http_status: int | None
    retryable: bool


@dataclass(frozen=True)
class CircuitPermit:
    state: str
    probe_token: str = ''


_CIRCUIT_ACQUIRE_LUA = r"""
local state = redis.call('HGET', KEYS[1], 'state')
local now = tonumber(ARGV[1])
local probe_token = ARGV[2]
local probe_ms = tonumber(ARGV[3])

if not state or state == 'closed' then
  return {1, 'closed', '', 0}
end

if state == 'open' then
  local open_until = tonumber(redis.call('HGET', KEYS[1], 'open_until') or '0')
  if now < open_until then
    return {0, 'open', '', open_until - now}
  end
  redis.call('HSET', KEYS[1], 'state', 'half_open', 'probe_token', probe_token,
             'probe_expires_at', now + probe_ms)
  redis.call('PEXPIRE', KEYS[1], probe_ms)
  return {1, 'half_open', probe_token, 0}
end

local probe_expires_at = tonumber(redis.call('HGET', KEYS[1], 'probe_expires_at') or '0')
if now >= probe_expires_at then
  redis.call('HSET', KEYS[1], 'probe_token', probe_token,
             'probe_expires_at', now + probe_ms)
  redis.call('PEXPIRE', KEYS[1], probe_ms)
  return {1, 'half_open', probe_token, 0}
end
return {0, 'half_open', '', probe_expires_at - now}
"""


_CIRCUIT_SUCCESS_LUA = r"""
local state = redis.call('HGET', KEYS[1], 'state')
if not state or state == 'closed' then
  redis.call('DEL', KEYS[1])
  return 1
end
if state == 'half_open' and redis.call('HGET', KEYS[1], 'probe_token') == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""


_CIRCUIT_FAILURE_LUA = r"""
local state = redis.call('HGET', KEYS[1], 'state')
local now = tonumber(ARGV[1])
local threshold = tonumber(ARGV[2])
local open_ms = tonumber(ARGV[3])
local probe_token = ARGV[4]

if state == 'open' then
  return {'open', tonumber(redis.call('HGET', KEYS[1], 'open_until') or tostring(now + open_ms))}
end
if state == 'half_open' then
  if redis.call('HGET', KEYS[1], 'probe_token') ~= probe_token then
    return {'half_open', 0}
  end
  redis.call('HSET', KEYS[1], 'state', 'open', 'failures', threshold,
             'open_until', now + open_ms)
  redis.call('HDEL', KEYS[1], 'probe_token', 'probe_expires_at')
  redis.call('PEXPIRE', KEYS[1], open_ms * 2)
  return {'open', now + open_ms}
end

local failures = redis.call('HINCRBY', KEYS[1], 'failures', 1)
if failures >= threshold then
  redis.call('HSET', KEYS[1], 'state', 'open', 'open_until', now + open_ms)
  redis.call('PEXPIRE', KEYS[1], open_ms * 2)
  return {'open', now + open_ms}
end
redis.call('HSET', KEYS[1], 'state', 'closed')
redis.call('PEXPIRE', KEYS[1], open_ms * 4)
return {'closed', failures}
"""


class ModelCircuitBreaker:
    """Short-lived deployment circuit state stored in Coordination Redis.

    PostgreSQL request/attempt rows remain the durable accounting truth. Redis
    only coordinates the fast Closed/Open/Half-open decision across workers.
    """

    def __init__(self, redis_connection=None, *, clock_ms=None):
        self._redis_connection = redis_connection
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    @property
    def redis(self):
        if self._redis_connection is None:
            self._redis_connection = get_redis_connection('coordination')
        return self._redis_connection

    @staticmethod
    def _bounded_capability(deployment, name: str, default: int, minimum: int, maximum: int) -> int:
        raw = (deployment.capabilities or {}).get(name, default)
        if isinstance(raw, bool):
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return min(maximum, max(minimum, value))

    @staticmethod
    def _key(deployment) -> str:
        return build_redis_key(
            domain='coordination',
            resource='model-circuit',
            version='v1',
            parts=(str(deployment.pk),),
        )

    @staticmethod
    def _decode(value) -> str:
        return value.decode('utf-8') if isinstance(value, bytes) else str(value or '')

    def before_call(self, deployment) -> CircuitPermit:
        probe_ms = self._bounded_capability(
            deployment, 'circuit_half_open_probe_seconds', 15, 1, 120
        ) * 1000
        token = uuid.uuid4().hex
        try:
            result = self.redis.eval(
                _CIRCUIT_ACQUIRE_LUA,
                1,
                self._key(deployment),
                self._clock_ms(),
                token,
                probe_ms,
            )
        except Exception as exc:
            raise GatewayCoordinationUnavailable(
                'model_gateway_coordination_unavailable'
            ) from exc
        allowed = bool(int(result[0]))
        state = self._decode(result[1])
        permit = CircuitPermit(state=state, probe_token=self._decode(result[2]))
        if not allowed:
            raise GatewayCircuitOpen(int(result[3] or 1))
        return permit

    def record_success(self, deployment, permit: CircuitPermit) -> None:
        try:
            self.redis.eval(
                _CIRCUIT_SUCCESS_LUA,
                1,
                self._key(deployment),
                permit.probe_token,
            )
        except Exception:
            # The durable result and ledger must not be rolled back because a
            # best-effort breaker reset could not reach Coordination Redis.
            return

    def record_failure(self, deployment, permit: CircuitPermit) -> None:
        threshold = self._bounded_capability(
            deployment, 'circuit_failure_threshold', 3, 1, 20
        )
        open_ms = self._bounded_capability(
            deployment, 'circuit_open_seconds', 30, 1, 600
        ) * 1000
        try:
            self.redis.eval(
                _CIRCUIT_FAILURE_LUA,
                1,
                self._key(deployment),
                self._clock_ms(),
                threshold,
                open_ms,
                permit.probe_token,
            )
        except Exception:
            # The provider failure is already represented in PostgreSQL. A
            # Redis outage must not hide or replace that durable error.
            return


_OPENAI_CLIENTS = OrderedDict()
_OPENAI_CLIENTS_LOCK = threading.Lock()
_OPENAI_CLIENTS_MAX = 64
_REQUESTS_LOCAL = threading.local()


def _pooled_openai_client(target: ExecutionTarget):
    secret_fingerprint = hashlib.sha256(target.api_key.encode('utf-8')).hexdigest()
    cache_key = (
        str(target.deployment.pk),
        target.deployment.base_url or '',
        secret_fingerprint,
    )
    with _OPENAI_CLIENTS_LOCK:
        existing = _OPENAI_CLIENTS.get(cache_key)
        if existing is not None:
            _OPENAI_CLIENTS.move_to_end(cache_key)
            return existing
        client = OpenAI(
            api_key=target.api_key,
            base_url=target.deployment.base_url or None,
            # Retries are explicitly classified and metered by this gateway.
            max_retries=0,
        )
        _OPENAI_CLIENTS[cache_key] = client
        while len(_OPENAI_CLIENTS) > _OPENAI_CLIENTS_MAX:
            # Do not close here: another worker thread may still hold the
            # evicted client for an in-flight request. Once its local reference
            # is released, the SDK client can be garbage-collected safely.
            _OPENAI_CLIENTS.popitem(last=False)
        return client


def _pooled_requests_session():
    session = getattr(_REQUESTS_LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        _REQUESTS_LOCAL.session = session
    return session


def _month_start():
    today = timezone.localdate()
    return today.replace(day=1)


def _estimate_tokens(value) -> int:
    if isinstance(value, list):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value or '')
    if not text:
        return 0
    return max(1, len(text) // 4)


def _bounded_integer(value, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _response_text(response) -> str:
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        return str(response.get('text') or response.get('content') or '').strip()
    for attribute in ('text', 'content'):
        value = getattr(response, attribute, None)
        if value:
            return str(value).strip()
    return ''


def _usage_tokens(response) -> tuple[int, int]:
    usage = getattr(response, 'usage', None)
    if usage is None and isinstance(response, dict):
        usage = response.get('usage')
    if isinstance(usage, dict):
        input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens') or 0
        output_tokens = usage.get('output_tokens') or usage.get('completion_tokens') or 0
    else:
        input_tokens = (
            getattr(usage, 'input_tokens', 0) or getattr(usage, 'prompt_tokens', 0) or 0
        )
        output_tokens = (
            getattr(usage, 'output_tokens', 0) or getattr(usage, 'completion_tokens', 0) or 0
        )
    return max(0, int(input_tokens)), max(0, int(output_tokens))


def _read_audio_input(audio) -> bytes:
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, (bytearray, memoryview)):
        return bytes(audio)
    reader = getattr(audio, 'read', None)
    if not callable(reader):
        raise GatewayExecutionError('audio_input_must_be_bytes_or_file')
    position = None
    try:
        position = audio.tell()
    except Exception:
        pass
    data = reader()
    if position is not None:
        try:
            audio.seek(position)
        except Exception:
            pass
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise GatewayExecutionError('audio_input_must_be_binary')
    return bytes(data)


def _safe_audio_filename(value: str | None) -> str:
    raw = str(value or 'audio.bin').replace('\\', '/')
    filename = os.path.basename(raw).strip()
    filename = ''.join(
        character for character in filename
        if ord(character) >= 32 and character not in {'"', "'"}
    )
    return (filename or 'audio.bin')[:120]


def _response_audio_bytes(response) -> bytes:
    if isinstance(response, bytes):
        return response
    if isinstance(response, (bytearray, memoryview)):
        return bytes(response)
    reader = getattr(response, 'read', None)
    if callable(reader):
        value = reader()
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
    value = getattr(response, 'content', None)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise GatewayExecutionError('tts_response_not_binary')


class GatewayExecutor:
    """Task-oriented model gateway with routing, BYOK isolation and metering."""

    def __init__(self, user=None, *, circuit_breaker=None):
        self.user = user if getattr(user, 'is_authenticated', False) else None
        self.circuit_breaker = circuit_breaker or ModelCircuitBreaker()

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
                total_timeout=policy.total_timeout_seconds,
            ))
        if not resolved:
            raise GatewayExecutionError(f'no_available_deployment:{alias_slug}')
        return resolved

    def _ledger(
        self,
        alias,
        task_name,
        input_summary,
        *,
        total_timeout: int,
        input_units: int | None = None,
        input_unit: str = 'estimated_tokens',
    ) -> ModelRequestLedger:
        safe_input_units = max(
            0,
            int(_estimate_tokens(input_summary) if input_units is None else input_units),
        )
        ledger_metadata = {
            'input_units': safe_input_units,
            'input_unit': str(input_unit or 'estimated_tokens')[:32],
            'total_deadline_ms': max(1, int(total_timeout * 1000)),
        }
        try:
            self._budget()
        except GatewayBudgetExceeded as exc:
            ModelRequestLedger.objects.create(
                user=self.user,
                alias=alias,
                task_name=task_name,
                status=ModelRequestLedger.Status.REJECTED,
                error_code=str(exc),
                metadata=ledger_metadata,
                completed_at=timezone.now(),
            )
            raise
        return ModelRequestLedger.objects.create(
            user=self.user,
            alias=alias,
            task_name=task_name,
            metadata=ledger_metadata,
        )

    def _client(self, target: ExecutionTarget):
        return _pooled_openai_client(target)

    @staticmethod
    def _error_details(exc):
        status_code = getattr(exc, 'status_code', None)
        if status_code is None:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        try:
            status_code = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            status_code = None
        error_name = type(exc).__name__
        if isinstance(exc, GatewayCircuitOpen):
            return ProviderFailure('circuit_open', 'circuit', status_code, True)
        if isinstance(exc, GatewayCoordinationUnavailable):
            return ProviderFailure('coordination_unavailable', 'coordination', status_code, False)
        if isinstance(exc, GatewayDeadlineExceeded) or str(exc) == 'model_gateway_total_deadline_exceeded':
            return ProviderFailure('total_deadline_exceeded', 'deadline', status_code, False)
        if status_code in {401, 403} or error_name in {'AuthenticationError', 'PermissionDeniedError'}:
            return ProviderFailure('provider_authentication_error', 'authentication', status_code, False)
        if status_code in {400, 404, 409, 422} or error_name in {
            'BadRequestError', 'NotFoundError', 'ConflictError', 'UnprocessableEntityError'
        }:
            return ProviderFailure('provider_invalid_request', 'invalid_request', status_code, False)
        if status_code == 429 or error_name == 'RateLimitError':
            return ProviderFailure('provider_rate_limited', 'rate_limit', status_code, True)
        if (
            isinstance(exc, (TimeoutError, requests.Timeout)) or
            error_name in {'APITimeoutError', 'ReadTimeout', 'ConnectTimeout'}
        ):
            return ProviderFailure('provider_timeout', 'timeout', status_code, True)
        if (
            isinstance(exc, (ConnectionError, requests.ConnectionError)) or
            error_name in {'APIConnectionError', 'ConnectionError'}
        ):
            return ProviderFailure('provider_connection_error', 'network', status_code, True)
        if status_code is not None and 500 <= status_code <= 599:
            return ProviderFailure('provider_temporary_server_error', 'server', status_code, True)
        return ProviderFailure(error_name[:120], 'unknown', status_code, False)

    @staticmethod
    def _attempt_cost(target, input_tokens: int, output_tokens: int) -> Decimal:
        input_cost = Decimal(max(0, input_tokens)) * target.deployment.input_price_per_million / Decimal(1_000_000)
        output_cost = Decimal(max(0, output_tokens)) * target.deployment.output_price_per_million / Decimal(1_000_000)
        return input_cost + output_cost

    def _record_attempt(
        self,
        ledger,
        target,
        attempt_number,
        *,
        started,
        success,
        error=None,
        input_tokens=0,
        output_tokens=0,
        provider_request_id='',
        timeout_seconds=0,
        provider_called=True,
        metadata=None,
    ) -> ProviderFailure:
        failure = ProviderFailure('', '', None, False) if not error else self._error_details(error)
        ModelAttempt.objects.update_or_create(
            request=ledger,
            attempt_number=attempt_number,
            defaults={
                'deployment': target.deployment,
                'status': ModelAttempt.Status.SUCCEEDED if success else ModelAttempt.Status.FAILED,
                'retryable': failure.retryable,
                'error_category': failure.category,
                'error_code': failure.code,
                'http_status': failure.http_status,
                'provider_request_id': str(provider_request_id or '')[:200],
                'input_tokens': max(0, input_tokens),
                'output_tokens': max(0, output_tokens),
                'estimated_cost': self._attempt_cost(target, input_tokens, output_tokens),
                'latency_ms': int((time.perf_counter() - started) * 1000),
                'metadata': {
                    'provider_called': bool(provider_called),
                    'timeout_ms': max(0, int(float(timeout_seconds or 0) * 1000)),
                    **(metadata or {}),
                },
                'completed_at': timezone.now(),
            },
        )
        return failure

    def _record_circuit_failure(self, target, permit, failure: ProviderFailure) -> None:
        if permit is None:
            return
        if failure.retryable:
            self.circuit_breaker.record_failure(target.deployment, permit)
        elif failure.category not in {'deadline', 'coordination', 'circuit'}:
            # A deterministic provider response (for example 400/401 or an
            # invalid output contract) proves the endpoint is reachable. It
            # must not accumulate transient circuit failures.
            self.circuit_breaker.record_success(target.deployment, permit)

    @staticmethod
    def _remaining_timeout(started, target) -> float:
        remaining = float(target.total_timeout) - (time.perf_counter() - started)
        if remaining <= 0:
            raise GatewayDeadlineExceeded('model_gateway_total_deadline_exceeded')
        return min(float(target.timeout), remaining)

    @transaction.atomic
    def _complete(self, ledger, target, *, started, input_tokens, output_tokens, success, error='', fallback_count=0):
        totals = ledger.attempts.aggregate(
            input_tokens=Sum('input_tokens'),
            output_tokens=Sum('output_tokens'),
            estimated_cost=Sum('estimated_cost'),
        )
        actual_input_tokens = int(
            totals['input_tokens'] if totals['input_tokens'] is not None else (input_tokens or 0)
        )
        actual_output_tokens = int(
            totals['output_tokens'] if totals['output_tokens'] is not None else (output_tokens or 0)
        )
        cost = Decimal(
            totals['estimated_cost'] if totals['estimated_cost'] is not None else 0
        )
        ledger.deployment = target.deployment
        ledger.status = ModelRequestLedger.Status.SUCCEEDED if success else ModelRequestLedger.Status.FAILED
        ledger.input_tokens = max(0, actual_input_tokens)
        ledger.output_tokens = max(0, actual_output_tokens)
        ledger.estimated_cost = cost
        ledger.latency_ms = int((time.perf_counter() - started) * 1000)
        ledger.fallback_count = fallback_count
        ledger.error_code = str(error)[:120]
        ledger.completed_at = timezone.now()
        ledger.save()
        if self.user and (actual_input_tokens or actual_output_tokens or cost):
            budget = UsageBudget.objects.select_for_update().filter(user=self.user, is_active=True).first()
            if budget:
                budget.used_input_tokens += max(0, actual_input_tokens)
                budget.used_output_tokens += max(0, actual_output_tokens)
                budget.used_cost += cost
                budget.save(update_fields=['used_input_tokens', 'used_output_tokens', 'used_cost', 'updated_at'])
        target.deployment.last_health_status = 'healthy' if success else 'degraded'
        target.deployment.last_health_at = timezone.now()
        target.deployment.save(update_fields=['last_health_status', 'last_health_at', 'updated_at'])

    def chat_json(self, alias_slug: str, messages: list[dict], *, task_name: str | None = None, max_tokens=1024, temperature=0.3) -> dict:
        targets = self.targets(alias_slug)
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            messages,
            total_timeout=targets[0].total_timeout,
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                with concurrency_lease(
                    scope='model-deployment',
                    identity=str(target.deployment_id if hasattr(target, 'deployment_id') else target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    response = self._client(target).chat.completions.create(
                        model=target.deployment.remote_model,
                        messages=messages,
                        stream=False,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format={'type': 'json_object'},
                        timeout=attempt_timeout,
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
                self._record_attempt(
                    ledger, target, index + 1, started=attempt_started, success=True,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    provider_request_id=getattr(response, 'id', ''),
                    timeout_seconds=attempt_timeout,
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(ledger, target, started=started, input_tokens=input_tokens, output_tokens=output_tokens, success=True, fallback_count=index)
                return result
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=_estimate_tokens(messages),
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'chat_json_failed')

    def chat_text(
        self,
        alias_slug: str,
        messages: list[dict],
        *,
        task_name: str | None = None,
        max_tokens=1024,
        temperature=0.7,
    ) -> str:
        targets = self.targets(alias_slug)
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            messages,
            total_timeout=targets[0].total_timeout,
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                with concurrency_lease(
                    scope='model-deployment',
                    identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    response = self._client(target).chat.completions.create(
                        model=target.deployment.remote_model,
                        messages=messages,
                        stream=False,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        timeout=attempt_timeout,
                    )
                content = (response.choices[0].message.content or '').strip()
                if not content:
                    raise GatewayExecutionError('chat_empty_response')
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) or _estimate_tokens(messages)
                output_tokens = getattr(usage, 'completion_tokens', 0) or _estimate_tokens(content)
                self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider_request_id=getattr(response, 'id', ''),
                    timeout_seconds=attempt_timeout,
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(
                    ledger,
                    target,
                    started=started,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    success=True,
                    fallback_count=index,
                )
                return content
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=_estimate_tokens(messages),
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'chat_text_failed')

    def chat_stream(self, alias_slug: str, messages: list[dict], *, task_name: str | None = None, max_tokens=1024, temperature=0.7):
        targets = self.targets(alias_slug)
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            messages,
            total_timeout=targets[0].total_timeout,
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            chunks = []
            emitted_any = False
            provider_request_id = ''
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                with concurrency_lease(
                    scope='model-deployment',
                    identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    stream = self._client(target).chat.completions.create(
                        model=target.deployment.remote_model,
                        messages=messages,
                        stream=True,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        timeout=attempt_timeout,
                    )
                    for chunk in stream:
                        # The SDK read timeout protects stalled reads; this
                        # explicit check also enforces the shared wall-clock
                        # deadline when chunks keep arriving continuously.
                        self._remaining_timeout(started, target)
                        provider_request_id = provider_request_id or getattr(chunk, 'id', '')
                        value = chunk.choices[0].delta.content or ''
                        if value:
                            chunks.append(value)
                            emitted_any = True
                            yield value
                self._record_attempt(
                    ledger, target, index + 1, started=attempt_started, success=True,
                    input_tokens=_estimate_tokens(messages), output_tokens=_estimate_tokens(''.join(chunks)),
                    provider_request_id=provider_request_id,
                    timeout_seconds=attempt_timeout,
                )
                self.circuit_breaker.record_success(target.deployment, permit)
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
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    input_tokens=_estimate_tokens(messages),
                    output_tokens=_estimate_tokens(''.join(chunks)),
                    provider_request_id=provider_request_id,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if emitted_any:
                    self._complete(ledger, target, started=started, input_tokens=_estimate_tokens(messages), output_tokens=_estimate_tokens(''.join(chunks)), success=False, error=last_error, fallback_count=index)
                    raise GatewayExecutionError(last_error) from exc
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=_estimate_tokens(messages),
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'chat_stream_failed')

    def embed_text(self, alias_slug: str, text: str, *, task_name: str | None = None):
        targets = self.targets(alias_slug)
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            text,
            total_timeout=targets[0].total_timeout,
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                with concurrency_lease(
                    scope='model-deployment', identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    response = self._client(target).embeddings.create(
                        model=target.deployment.remote_model,
                        input=(text or '')[:16000],
                        timeout=attempt_timeout,
                    )
                vector = response.data[0].embedding
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) or _estimate_tokens(text)
                self._record_attempt(
                    ledger, target, index + 1, started=attempt_started,
                    success=True, input_tokens=input_tokens,
                    provider_request_id=getattr(response, 'id', ''),
                    timeout_seconds=attempt_timeout,
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(ledger, target, started=started, input_tokens=input_tokens, output_tokens=0, success=True, fallback_count=index)
                return vector, target.deployment.remote_model, {'alias': alias_slug, 'deployment': target.deployment.name}
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=_estimate_tokens(text),
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'embedding_failed')

    def rerank(self, alias_slug: str, query: str, documents: Iterable[str], *, top_n=4, task_name: str | None = None):
        docs = [str(item or '') for item in documents]
        targets = self.targets(alias_slug)
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            [query, *docs],
            total_timeout=targets[0].total_timeout,
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                url = target.deployment.base_url.rstrip('/')
                payload = {'model': target.deployment.remote_model, 'query': query, 'documents': docs, 'top_n': min(max(1, top_n), len(docs)), 'return_documents': False}
                with concurrency_lease(
                    scope='model-deployment', identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    response = _pooled_requests_session().post(
                        url,
                        json=payload,
                        headers={'Authorization': f'Bearer {target.api_key}'},
                        timeout=attempt_timeout,
                    )
                    response.raise_for_status()
                data = response.json()
                results = data.get('results') or data.get('output', {}).get('results') or []
                self._record_attempt(
                    ledger, target, index + 1, started=attempt_started,
                    success=True, input_tokens=_estimate_tokens([query, *docs]),
                    provider_request_id=(
                        data.get('id') or response.headers.get('x-request-id', '')
                    ),
                    timeout_seconds=attempt_timeout,
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(ledger, target, started=started, input_tokens=_estimate_tokens([query, *docs]), output_tokens=0, success=True, fallback_count=index)
                return results, {'alias': alias_slug, 'deployment': target.deployment.name}
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=_estimate_tokens([query, *docs]),
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'rerank_failed')

    def transcribe_audio(
        self,
        alias_slug: str,
        audio,
        *,
        filename: str = 'audio.webm',
        content_type: str = 'audio/webm',
        language: str | None = None,
        prompt: str | None = None,
        task_name: str | None = None,
    ) -> tuple[str, dict]:
        """Transcribe bytes/file input without persisting audio in the ledger."""

        targets = self.targets(alias_slug)
        audio_bytes = _read_audio_input(audio)
        max_audio_bytes = min(
            _bounded_integer(
                (target.deployment.capabilities or {}).get('max_audio_bytes'),
                default=25 * 1024 * 1024,
                minimum=1,
                maximum=100 * 1024 * 1024,
            )
            for target in targets
        )
        if not audio_bytes:
            raise GatewayExecutionError('audio_input_empty')
        if len(audio_bytes) > max_audio_bytes:
            raise GatewayExecutionError('audio_input_too_large')
        safe_filename = _safe_audio_filename(filename)
        safe_content_type = str(content_type or 'application/octet-stream').strip()
        if (
            len(safe_content_type) > 100 or
            '\r' in safe_content_type or
            '\n' in safe_content_type or
            not (
                safe_content_type.startswith('audio/') or
                safe_content_type == 'video/webm' or
                safe_content_type == 'application/octet-stream'
            )
        ):
            raise GatewayExecutionError('audio_content_type_invalid')
        safe_language = str(language or '').strip()[:16]
        safe_prompt = str(prompt or '')[:1000]
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            {'audio_bytes': len(audio_bytes)},
            total_timeout=targets[0].total_timeout,
            input_units=len(audio_bytes),
            input_unit='bytes',
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                params = {
                    'model': target.deployment.remote_model,
                    'file': (safe_filename, audio_bytes, safe_content_type),
                    'timeout': attempt_timeout,
                }
                if safe_language:
                    params['language'] = safe_language
                if safe_prompt:
                    params['prompt'] = safe_prompt
                with concurrency_lease(
                    scope='model-deployment',
                    identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    params['timeout'] = attempt_timeout
                    response = self._client(target).audio.transcriptions.create(**params)
                transcript = _response_text(response)
                if not transcript:
                    raise GatewayExecutionError('asr_empty_transcript')
                input_tokens, output_tokens = _usage_tokens(response)
                request_id = getattr(response, 'id', '') or getattr(response, '_request_id', '')
                self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider_request_id=request_id,
                    timeout_seconds=attempt_timeout,
                    metadata={'input_bytes': len(audio_bytes)},
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(
                    ledger,
                    target,
                    started=started,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    success=True,
                    fallback_count=index,
                )
                return transcript, {
                    'alias': alias_slug,
                    'deployment': target.deployment.name,
                    'provider': target.deployment.provider,
                    'model': target.deployment.remote_model,
                    'provider_request_id': str(request_id or ''),
                }
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                    metadata={'input_bytes': len(audio_bytes)},
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'asr_failed')

    def synthesize_speech(
        self,
        alias_slug: str,
        text: str,
        *,
        voice: str = 'alloy',
        response_format: str = 'mp3',
        speed: float | None = None,
        task_name: str | None = None,
    ) -> tuple[bytes, dict]:
        """Synthesize speech while recording only text length and output size."""

        targets = self.targets(alias_slug)
        value = str(text or '')
        max_text_chars = min(
            _bounded_integer(
                (target.deployment.capabilities or {}).get('max_tts_chars'),
                default=10_000,
                minimum=1,
                maximum=100_000,
            )
            for target in targets
        )
        if not value.strip():
            raise GatewayExecutionError('tts_text_empty')
        if len(value) > max_text_chars:
            raise GatewayExecutionError('tts_text_too_long')
        safe_voice = str(voice or 'alloy').strip()
        if not safe_voice or len(safe_voice) > 64 or '\r' in safe_voice or '\n' in safe_voice:
            raise GatewayExecutionError('tts_voice_invalid')
        safe_format = str(response_format or 'mp3').strip().lower().lstrip('.')
        if safe_format not in {'mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'}:
            raise GatewayExecutionError('tts_response_format_invalid')
        safe_speed = None
        if speed is not None:
            try:
                safe_speed = float(speed)
            except (TypeError, ValueError) as exc:
                raise GatewayExecutionError('tts_speed_invalid') from exc
            if not 0.25 <= safe_speed <= 4.0:
                raise GatewayExecutionError('tts_speed_invalid')
        ledger = self._ledger(
            targets[0].alias,
            task_name or alias_slug,
            {'text_chars': len(value)},
            total_timeout=targets[0].total_timeout,
            input_units=len(value),
            input_unit='characters',
        )
        started = time.perf_counter()
        last_error = ''
        last_target = targets[0]
        attempted = 0
        for index, target in enumerate(targets):
            attempted += 1
            last_target = target
            attempt_started = time.perf_counter()
            permit = None
            attempt_timeout = 0
            try:
                attempt_timeout = self._remaining_timeout(started, target)
                permit = self.circuit_breaker.before_call(target.deployment)
                params = {
                    'model': target.deployment.remote_model,
                    'voice': safe_voice,
                    'input': value,
                    'response_format': safe_format,
                    'timeout': attempt_timeout,
                }
                if safe_speed is not None:
                    params['speed'] = safe_speed
                with concurrency_lease(
                    scope='model-deployment',
                    identity=str(target.deployment.pk),
                    limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                    lease_seconds=max(1, int(attempt_timeout) + 10),
                ):
                    attempt_timeout = self._remaining_timeout(started, target)
                    params['timeout'] = attempt_timeout
                    response = self._client(target).audio.speech.create(**params)
                    audio_bytes = _response_audio_bytes(response)
                max_output_bytes = _bounded_integer(
                    (target.deployment.capabilities or {}).get('max_tts_output_bytes'),
                    default=25 * 1024 * 1024,
                    minimum=1,
                    maximum=100 * 1024 * 1024,
                )
                if not audio_bytes:
                    raise GatewayExecutionError('tts_empty_audio')
                if len(audio_bytes) > max_output_bytes:
                    raise GatewayExecutionError('tts_output_too_large')
                input_tokens, output_tokens = _usage_tokens(response)
                request_id = getattr(response, 'id', '') or getattr(response, '_request_id', '')
                self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider_request_id=request_id,
                    timeout_seconds=attempt_timeout,
                    metadata={
                        'input_characters': len(value),
                        'output_bytes': len(audio_bytes),
                        'response_format': safe_format,
                    },
                )
                self.circuit_breaker.record_success(target.deployment, permit)
                self._complete(
                    ledger,
                    target,
                    started=started,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    success=True,
                    fallback_count=index,
                )
                return audio_bytes, {
                    'alias': alias_slug,
                    'deployment': target.deployment.name,
                    'provider': target.deployment.provider,
                    'model': target.deployment.remote_model,
                    'provider_request_id': str(request_id or ''),
                    'response_format': safe_format,
                }
            except Exception as exc:
                failure = self._record_attempt(
                    ledger,
                    target,
                    index + 1,
                    started=attempt_started,
                    success=False,
                    error=exc,
                    timeout_seconds=attempt_timeout,
                    provider_called=permit is not None,
                    metadata={
                        'input_characters': len(value),
                        'response_format': safe_format,
                    },
                )
                self._record_circuit_failure(target, permit, failure)
                last_error = failure.code
                if not failure.retryable:
                    break
        self._complete(
            ledger,
            last_target,
            started=started,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error=last_error,
            fallback_count=max(0, attempted - 1),
        )
        raise GatewayExecutionError(last_error or 'tts_failed')

    def synthesize_speech_stream(
        self,
        alias_slug: str,
        text: str,
        *,
        voice: str = 'alloy',
        response_format: str = 'pcm',
        speed: float | None = None,
        task_name: str | None = None,
        chunk_size: int = 4096,
    ):
        """Yield provider audio chunks while preserving the shared ledger.

        Fallback is allowed only before the first audio chunk. Once playback can
        begin, switching providers would create an audible voice discontinuity.
        """
        targets = self.targets(alias_slug)
        value = str(text or '')
        if not value.strip():
            raise GatewayExecutionError('tts_text_empty')
        max_text_chars = min(_bounded_integer(
            (target.deployment.capabilities or {}).get('max_tts_chars'),
            default=10_000, minimum=1, maximum=100_000,
        ) for target in targets)
        if len(value) > max_text_chars:
            raise GatewayExecutionError('tts_text_too_long')
        safe_voice = str(voice or 'alloy').strip()
        if not safe_voice or len(safe_voice) > 64 or '\r' in safe_voice or '\n' in safe_voice:
            raise GatewayExecutionError('tts_voice_invalid')
        safe_format = str(response_format or 'pcm').strip().lower().lstrip('.')
        if safe_format not in {'opus', 'pcm'}:
            raise GatewayExecutionError('tts_stream_format_invalid')
        safe_speed = None
        if speed is not None:
            try:
                safe_speed = float(speed)
            except (TypeError, ValueError) as exc:
                raise GatewayExecutionError('tts_speed_invalid') from exc
            if not 0.25 <= safe_speed <= 4.0:
                raise GatewayExecutionError('tts_speed_invalid')
        safe_chunk_size = _bounded_integer(chunk_size, default=4096, minimum=512, maximum=64 * 1024)

        metadata = {
            'alias': alias_slug,
            'response_format': safe_format,
            'sample_rate': 24_000 if safe_format == 'pcm' else None,
        }

        def iterator():
            ledger = self._ledger(
                targets[0].alias,
                task_name or alias_slug,
                {'text_chars': len(value), 'streaming': True},
                total_timeout=targets[0].total_timeout,
                input_units=len(value),
                input_unit='characters',
            )
            started = time.perf_counter()
            last_error = ''
            last_target = targets[0]
            attempted = 0
            emitted_any = False
            for index, target in enumerate(targets):
                attempted += 1
                last_target = target
                attempt_started = time.perf_counter()
                permit = None
                attempt_timeout = 0
                output_bytes = 0
                response = None
                try:
                    attempt_timeout = self._remaining_timeout(started, target)
                    permit = self.circuit_breaker.before_call(target.deployment)
                    params = {
                        'model': target.deployment.remote_model,
                        'voice': safe_voice,
                        'input': value,
                        'response_format': safe_format,
                        'timeout': attempt_timeout,
                    }
                    if safe_speed is not None:
                        params['speed'] = safe_speed
                    with concurrency_lease(
                        scope='model-deployment', identity=str(target.deployment.pk),
                        limit=int((target.deployment.capabilities or {}).get('max_concurrency') or 8),
                        lease_seconds=max(1, int(attempt_timeout) + 10),
                    ):
                        stream_factory = self._client(target).audio.speech.with_streaming_response.create
                        with stream_factory(**params) as response:
                            metadata.update({
                                'deployment': target.deployment.name,
                                'provider': target.deployment.provider,
                                'model': target.deployment.remote_model,
                            })
                            for chunk in response.iter_bytes(chunk_size=safe_chunk_size):
                                if not chunk:
                                    continue
                                emitted_any = True
                                output_bytes += len(chunk)
                                yield chunk
                    if not emitted_any:
                        raise GatewayExecutionError('tts_empty_audio')
                    request_id = ''
                    if response is not None:
                        request_id = getattr(response, '_request_id', '') or getattr(response, 'request_id', '')
                    self._record_attempt(
                        ledger, target, index + 1, started=attempt_started, success=True,
                        input_tokens=0, output_tokens=0, provider_request_id=request_id,
                        timeout_seconds=attempt_timeout,
                        metadata={'input_characters': len(value), 'output_bytes': output_bytes, 'response_format': safe_format, 'streaming': True},
                    )
                    self.circuit_breaker.record_success(target.deployment, permit)
                    self._complete(ledger, target, started=started, input_tokens=0, output_tokens=0, success=True, fallback_count=index)
                    return
                except GeneratorExit:
                    self._record_attempt(
                        ledger, target, index + 1, started=attempt_started, success=False,
                        error=GatewayExecutionError('tts_stream_canceled'), timeout_seconds=attempt_timeout,
                        provider_called=permit is not None,
                        metadata={'input_characters': len(value), 'output_bytes': output_bytes, 'response_format': safe_format, 'streaming': True, 'canceled': True},
                    )
                    self._complete(ledger, target, started=started, input_tokens=0, output_tokens=0, success=False, error='tts_stream_canceled', fallback_count=index)
                    raise
                except Exception as exc:
                    failure = self._record_attempt(
                        ledger, target, index + 1, started=attempt_started, success=False,
                        error=exc, timeout_seconds=attempt_timeout, provider_called=permit is not None,
                        metadata={'input_characters': len(value), 'output_bytes': output_bytes, 'response_format': safe_format, 'streaming': True},
                    )
                    self._record_circuit_failure(target, permit, failure)
                    last_error = failure.code
                    if emitted_any or not failure.retryable:
                        break
            self._complete(
                ledger, last_target, started=started, input_tokens=0, output_tokens=0,
                success=False, error=last_error, fallback_count=max(0, attempted - 1),
            )
            raise GatewayExecutionError(last_error or 'tts_failed')

        return iterator(), metadata
