from __future__ import annotations

import ipaddress
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from django.conf import settings
from django_redis import get_redis_connection
from rest_framework.exceptions import APIException

from .redis_keys import build_redis_key, opaque_identifier


class CapacityRejected(APIException):
    status_code = 429
    default_code = 'capacity_limited'

    def __init__(
        self,
        *,
        scope: str,
        retry_after_ms: int = 1000,
        overloaded=False,
        error_code: str | None = None,
    ):
        from .middleware import get_current_correlation_id

        self.status_code = 503 if overloaded else 429
        super().__init__({
            'code': error_code or ('dependency_unavailable' if overloaded else self.default_code),
            'message': '当前处理容量已满，请稍后重试。',
            'retryable': True,
            'retry_after_ms': max(1, int(retry_after_ms)),
            'scope': scope,
            'correlation_id': get_current_correlation_id() or None,
        })


class RuntimePolicyConfigurationError(ValueError):
    """Fail-closed signal for malformed admission policy values."""


@dataclass(frozen=True)
class TokenDimension:
    scope: str
    identity: str
    capacity: int
    refill_per_minute: int
    requested: int = 1


@dataclass(frozen=True)
class TokenDecision:
    allowed: bool
    blocked_index: int = -1
    retry_after_ms: int = 0


_LEASE_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local lease_ms = tonumber(ARGV[1])
local owner = ARGV[2]
local limit = tonumber(ARGV[3])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local expires = now + lease_ms
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZSCORE', key, owner) then
  redis.call('ZADD', key, expires, owner)
elseif redis.call('ZCARD', key) >= limit then
  return 0
else
  redis.call('ZADD', key, expires, owner)
end
local latest = redis.call('ZREVRANGE', key, 0, 0, 'WITHSCORES')
if latest[2] then redis.call('PEXPIREAT', key, math.floor(tonumber(latest[2]))) end
return 1
"""

_LEASE_RENEW_SCRIPT = """
local key = KEYS[1]
local lease_ms = tonumber(ARGV[1])
local owner = ARGV[2]
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if not redis.call('ZSCORE', key, owner) then return 0 end
redis.call('ZADD', key, now + lease_ms, owner)
local latest = redis.call('ZREVRANGE', key, 0, 0, 'WITHSCORES')
if latest[2] then redis.call('PEXPIREAT', key, math.floor(tonumber(latest[2]))) end
return 1
"""

_LEASE_RELEASE_SCRIPT = """
local key = KEYS[1]
local owner = ARGV[1]
if redis.call('ZREM', key, owner) == 0 then return 0 end
if redis.call('ZCARD', key) == 0 then
  redis.call('DEL', key)
else
  local latest = redis.call('ZREVRANGE', key, 0, 0, 'WITHSCORES')
  if latest[2] then redis.call('PEXPIREAT', key, math.floor(tonumber(latest[2]))) end
end
return 1
"""

_MULTI_TOKEN_BUCKET_SCRIPT = """
local count = #KEYS
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local states = {}
local blocked_index = 0
local retry_after = 0

for index = 1, count do
  local offset = (index - 1) * 4
  local capacity = tonumber(ARGV[offset + 1])
  local refill_per_ms = tonumber(ARGV[offset + 2])
  local requested = tonumber(ARGV[offset + 3])
  local ttl_ms = tonumber(ARGV[offset + 4])
  local values = redis.call('HMGET', KEYS[index], 'tokens', 'updated')
  local tokens = tonumber(values[1]) or capacity
  local updated = tonumber(values[2]) or now
  tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill_per_ms)
  states[index] = {tokens, ttl_ms, requested}
  if tokens < requested then
    local wait_ms = math.ceil((requested - tokens) / refill_per_ms)
    if wait_ms > retry_after then
      retry_after = wait_ms
      blocked_index = index
    end
  end
end

-- Persist refill state, but consume from no dimension unless every dimension
-- can admit the request.  This gives the caller one all-or-nothing decision.
for index = 1, count do
  local tokens = states[index][1]
  if blocked_index == 0 then tokens = tokens - states[index][3] end
  redis.call('HSET', KEYS[index], 'tokens', tokens, 'updated', now)
  redis.call('PEXPIRE', KEYS[index], states[index][2])
end

if blocked_index ~= 0 then return {0, blocked_index, retry_after} end
return {1, 0, 0}
"""


def _lease_key(*, scope: str, identity: str) -> str:
    return build_redis_key(
        domain='coordination',
        resource='concurrency-lease',
        parts=(scope,),
        opaque_parts=(identity,),
    )


def _rate_key(*, scope: str, identity: str) -> str:
    return build_redis_key(
        domain='coordination',
        resource='rate-limit',
        parts=(scope,),
        opaque_parts=(identity,),
    )


def _lease_owner(member: str) -> str:
    return opaque_identifier(member, purpose='coordination-lease-owner')


def _bounded_integer(value, *, name: str, minimum: int, maximum: int, allow_string: bool) -> int:
    if isinstance(value, bool):
        raise RuntimePolicyConfigurationError(f'{name} must be an integer, not a boolean')
    if type(value) is int:
        parsed = value
    elif allow_string and isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise RuntimePolicyConfigurationError(f'{name} must be an integer')
    if not minimum <= parsed <= maximum:
        raise RuntimePolicyConfigurationError(f'{name} must be between {minimum} and {maximum}')
    return parsed


def runtime_policy_integer(
    policy: dict,
    key: str,
    *,
    setting_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Resolve a bounded integer; runtime JSON never receives string coercion."""

    if not isinstance(policy, dict):
        raise RuntimePolicyConfigurationError('reliability-admission config must be a JSON object')
    if key in policy:
        return _bounded_integer(
            policy[key],
            name=f'reliability-admission.{key}',
            minimum=minimum,
            maximum=maximum,
            allow_string=False,
        )
    return _bounded_integer(
        getattr(settings, setting_name, default),
        name=setting_name,
        minimum=minimum,
        maximum=maximum,
        allow_string=True,
    )


def _trusted_proxy(remote_address: str) -> bool:
    configured = getattr(settings, 'ADMISSION_TRUSTED_PROXY_IPS', ()) or ()
    if isinstance(configured, str):
        configured = [item.strip() for item in configured.split(',') if item.strip()]
    try:
        remote = ipaddress.ip_address(remote_address)
    except ValueError:
        return False
    for entry in configured:
        try:
            if remote in ipaddress.ip_network(str(entry), strict=False):
                return True
        except ValueError:
            continue
    return False


def _client_ip(request) -> str:
    remote = str(request.META.get('REMOTE_ADDR') or 'unknown').strip()
    forwarded = str(request.META.get('HTTP_X_FORWARDED_FOR') or '')
    if forwarded and _trusted_proxy(remote):
        candidate = forwarded.split(',')[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(remote))
    except ValueError:
        return 'unknown'


class AdmissionController:
    def __init__(self, redis=None):
        self.redis = redis if redis is not None else get_redis_connection('coordination')

    def acquire_lease(self, *, scope: str, identity: str, member: str, limit: int, lease_seconds: int) -> bool:
        safe_limit = _bounded_integer(
            limit, name='lease limit', minimum=1, maximum=100_000, allow_string=True
        )
        safe_seconds = _bounded_integer(
            lease_seconds, name='lease seconds', minimum=1, maximum=86_400, allow_string=True
        )
        result = self.redis.eval(
            _LEASE_ACQUIRE_SCRIPT,
            1,
            _lease_key(scope=scope, identity=str(identity)),
            safe_seconds * 1000,
            _lease_owner(member),
            safe_limit,
        )
        return bool(result)

    def renew_lease(self, *, scope: str, identity: str, member: str, lease_seconds: int) -> bool:
        safe_seconds = _bounded_integer(
            lease_seconds, name='lease seconds', minimum=1, maximum=86_400, allow_string=True
        )
        result = self.redis.eval(
            _LEASE_RENEW_SCRIPT,
            1,
            _lease_key(scope=scope, identity=str(identity)),
            safe_seconds * 1000,
            _lease_owner(member),
        )
        return bool(result)

    def release_lease(self, *, scope: str, identity: str, member: str) -> bool:
        result = self.redis.eval(
            _LEASE_RELEASE_SCRIPT,
            1,
            _lease_key(scope=scope, identity=str(identity)),
            _lease_owner(member),
        )
        return bool(result)

    def consume_multi_tokens(self, dimensions: list[TokenDimension]) -> TokenDecision:
        if not dimensions:
            raise ValueError('at least one token dimension is required')
        keys = []
        arguments: list[object] = []
        for dimension in dimensions:
            capacity = _bounded_integer(
                dimension.capacity,
                name=f'{dimension.scope} capacity',
                minimum=1,
                maximum=1_000_000,
                allow_string=True,
            )
            refill = _bounded_integer(
                dimension.refill_per_minute,
                name=f'{dimension.scope} refill',
                minimum=1,
                maximum=1_000_000,
                allow_string=True,
            )
            requested = _bounded_integer(
                dimension.requested,
                name=f'{dimension.scope} requested',
                minimum=1,
                maximum=capacity,
                allow_string=True,
            )
            refill_per_ms = refill / 60_000
            ttl_ms = min(604_800_000, max(60_000, int((capacity / refill) * 120_000)))
            keys.append(_rate_key(scope=dimension.scope, identity=str(dimension.identity)))
            arguments.extend((capacity, refill_per_ms, requested, ttl_ms))
        raw = self.redis.eval(
            _MULTI_TOKEN_BUCKET_SCRIPT,
            len(keys),
            *keys,
            *arguments,
        )
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            raise RuntimeError('coordination Redis returned an invalid admission decision')
        blocked = int(raw[1]) - 1 if int(raw[1]) else -1
        allowed = bool(int(raw[0]))
        if not allowed and not 0 <= blocked < len(dimensions):
            raise RuntimeError('coordination Redis returned an invalid blocked dimension')
        return TokenDecision(allowed, blocked, max(0, int(raw[2])))

    def consume_tokens(
        self,
        *,
        scope: str,
        identity: str,
        capacity: int,
        refill_per_minute: int,
        requested: int = 1,
    ) -> bool:
        decision = self.consume_multi_tokens([
            TokenDimension(
                scope=scope,
                identity=str(identity),
                capacity=capacity,
                refill_per_minute=refill_per_minute,
                requested=requested,
            )
        ])
        return decision.allowed


@contextmanager
def concurrency_lease(*, scope: str, identity: str, limit: int, lease_seconds: int = 120, member: str | None = None):
    token = member or str(uuid.uuid4())
    controller = AdmissionController()
    if not controller.acquire_lease(
        scope=scope,
        identity=identity,
        member=token,
        limit=limit,
        lease_seconds=lease_seconds,
    ):
        raise CapacityRejected(scope=scope)
    try:
        yield token
    finally:
        try:
            controller.release_lease(scope=scope, identity=identity, member=token)
        except Exception:
            # Lease expiry is the safety net when Redis is unavailable at release time.
            pass


def admit_expensive_operation(request, *, scope: str, company_id=None):
    """Fail closed and make all user/IP/company rate decisions atomically."""

    from django.utils import timezone
    from .models import IntegrationOutbox, RuntimePolicy

    policy = RuntimePolicy.objects.filter(
        key='reliability-admission',
        enabled=True,
    ).values_list('config', flat=True).first()
    if policy is None:
        policy = {}

    try:
        max_backlog = runtime_policy_integer(
            policy,
            'outbox_max_backlog',
            setting_name='ADMISSION_OUTBOX_MAX_BACKLOG',
            default=10_000,
            minimum=1,
            maximum=10_000_000,
        )
        max_age_seconds = runtime_policy_integer(
            policy,
            'outbox_max_age_seconds',
            setting_name='ADMISSION_OUTBOX_MAX_AGE_SECONDS',
            default=300,
            minimum=1,
            maximum=86_400,
        )
        user_capacity = runtime_policy_integer(
            policy,
            'user_per_minute',
            setting_name='ADMISSION_USER_PER_MINUTE',
            default=12,
            minimum=1,
            maximum=1_000_000,
        )
        ip_capacity = runtime_policy_integer(
            policy,
            'ip_per_minute',
            setting_name='ADMISSION_IP_PER_MINUTE',
            default=40,
            minimum=1,
            maximum=1_000_000,
        )
        company_capacity = None
        if company_id:
            company_capacity = runtime_policy_integer(
                policy,
                'company_per_minute',
                setting_name='ADMISSION_COMPANY_PER_MINUTE',
                default=60,
                minimum=1,
                maximum=1_000_000,
            )
    except RuntimePolicyConfigurationError as exc:
        raise CapacityRejected(
            scope=f'{scope}:invalid-runtime-policy',
            retry_after_ms=5000,
            overloaded=True,
            error_code='dependency_unavailable',
        ) from exc

    pending = IntegrationOutbox.objects.filter(
        status__in=[
            IntegrationOutbox.Status.PENDING,
            IntegrationOutbox.Status.PUBLISHING,
            IntegrationOutbox.Status.FAILED,
        ],
    )
    if pending.count() >= max_backlog:
        raise CapacityRejected(
            scope=f'{scope}:outbox-backlog',
            retry_after_ms=5000,
            overloaded=True,
            error_code='async_backpressure',
        )
    oldest = pending.order_by('available_at').values_list('available_at', flat=True).first()
    if oldest and (timezone.now() - oldest).total_seconds() > max_age_seconds:
        raise CapacityRejected(
            scope=f'{scope}:outbox-age',
            retry_after_ms=5000,
            overloaded=True,
            error_code='async_backpressure',
        )

    user_id = str(getattr(getattr(request, 'user', None), 'pk', '') or 'anonymous')
    dimensions = [
        TokenDimension(f'{scope}.user', user_id, user_capacity, user_capacity),
        TokenDimension(f'{scope}.ip', _client_ip(request), ip_capacity, ip_capacity),
    ]
    if company_id:
        dimensions.append(TokenDimension(
            f'{scope}.company', str(company_id), company_capacity, company_capacity
        ))
    try:
        decision = AdmissionController().consume_multi_tokens(dimensions)
        if not decision.allowed:
            blocked_scope = dimensions[decision.blocked_index].scope
            raise CapacityRejected(
                scope=blocked_scope,
                retry_after_ms=max(1_000, decision.retry_after_ms),
            )
    except CapacityRejected:
        raise
    except Exception as exc:
        raise CapacityRejected(
            scope=f'{scope}:coordination',
            retry_after_ms=2000,
            overloaded=True,
            error_code='dependency_unavailable',
        ) from exc
