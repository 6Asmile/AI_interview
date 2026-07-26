from __future__ import annotations

import time
import uuid
from contextlib import contextmanager

from django.conf import settings
from django_redis import get_redis_connection
from rest_framework.exceptions import APIException


class CapacityRejected(APIException):
    status_code = 429
    default_code = 'capacity_rejected'

    def __init__(self, *, scope: str, retry_after_ms: int = 1000, overloaded=False):
        self.status_code = 503 if overloaded else 429
        super().__init__({
            'code': 'system_overloaded' if overloaded else self.default_code,
            'message': '当前处理容量已满，请稍后重试。',
            'retryable': True,
            'retry_after_ms': retry_after_ms,
            'scope': scope,
        })


_LEASE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local member = ARGV[3]
local limit = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZSCORE', key, member) then
  redis.call('ZADD', key, expires, member)
  redis.call('PEXPIRE', key, math.max(1000, expires - now))
  return 1
end
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expires, member)
redis.call('PEXPIRE', key, math.max(1000, expires - now))
return 1
"""

_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_per_ms = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl_ms = tonumber(ARGV[5])
local values = redis.call('HMGET', key, 'tokens', 'updated')
local tokens = tonumber(values[1]) or capacity
local updated = tonumber(values[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill_per_ms)
if tokens < requested then
  redis.call('HMSET', key, 'tokens', tokens, 'updated', now)
  redis.call('PEXPIRE', key, ttl_ms)
  return 0
end
tokens = tokens - requested
redis.call('HMSET', key, 'tokens', tokens, 'updated', now)
redis.call('PEXPIRE', key, ttl_ms)
return 1
"""


def _prefix(domain: str, identity: str) -> str:
    env = str(getattr(settings, 'IFACEOFF_ENV', 'dev')).lower()
    return f'ifaceoff:{env}:coordination:{domain}:{identity}'


class AdmissionController:
    def __init__(self):
        self.redis = get_redis_connection('coordination')

    def acquire_lease(self, *, scope: str, identity: str, member: str, limit: int, lease_seconds: int) -> bool:
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + max(1, int(lease_seconds)) * 1000
        result = self.redis.eval(
            _LEASE_SCRIPT,
            1,
            _prefix(f'concurrency:{scope}', str(identity)),
            now_ms,
            expires_ms,
            member,
            max(1, int(limit)),
        )
        return bool(result)

    def release_lease(self, *, scope: str, identity: str, member: str) -> None:
        self.redis.zrem(_prefix(f'concurrency:{scope}', str(identity)), member)

    def consume_tokens(
        self,
        *,
        scope: str,
        identity: str,
        capacity: int,
        refill_per_minute: int,
        requested: int = 1,
    ) -> bool:
        now_ms = int(time.time() * 1000)
        refill_per_ms = float(refill_per_minute) / 60_000
        ttl_ms = max(60_000, int((capacity / max(refill_per_minute, 1)) * 120_000))
        result = self.redis.eval(
            _TOKEN_BUCKET_SCRIPT,
            1,
            _prefix(f'rate:{scope}', str(identity)),
            now_ms,
            max(1, int(capacity)),
            refill_per_ms,
            max(1, int(requested)),
            ttl_ms,
        )
        return bool(result)


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
    """Fail-closed, atomic admission for model work and other expensive writes."""

    from django.utils import timezone
    from .models import IntegrationOutbox, RuntimePolicy

    policy = RuntimePolicy.objects.filter(
        key='reliability-admission',
        enabled=True,
    ).values_list('config', flat=True).first() or {}

    pending = IntegrationOutbox.objects.filter(
        status__in=[
            IntegrationOutbox.Status.PENDING,
            IntegrationOutbox.Status.PUBLISHING,
            IntegrationOutbox.Status.FAILED,
        ],
    )
    max_backlog = int(policy.get('outbox_max_backlog') or getattr(settings, 'ADMISSION_OUTBOX_MAX_BACKLOG', 10000))
    if pending.count() >= max_backlog:
        raise CapacityRejected(scope=f'{scope}:outbox-backlog', retry_after_ms=5000, overloaded=True)
    oldest = pending.order_by('available_at').values_list('available_at', flat=True).first()
    max_age_seconds = int(policy.get('outbox_max_age_seconds') or getattr(settings, 'ADMISSION_OUTBOX_MAX_AGE_SECONDS', 300))
    if oldest and (timezone.now() - oldest).total_seconds() > max_age_seconds:
        raise CapacityRejected(scope=f'{scope}:outbox-age', retry_after_ms=5000, overloaded=True)

    controller = AdmissionController()
    user_id = str(getattr(getattr(request, 'user', None), 'pk', '') or 'anonymous')
    forwarded = str(request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    ip = forwarded or str(request.META.get('REMOTE_ADDR') or 'unknown')
    dimensions = [
        ('user', user_id, int(policy.get('user_per_minute') or getattr(settings, 'ADMISSION_USER_PER_MINUTE', 12))),
        ('ip', ip, int(policy.get('ip_per_minute') or getattr(settings, 'ADMISSION_IP_PER_MINUTE', 40))),
    ]
    if company_id:
        dimensions.append(('company', str(company_id), int(policy.get('company_per_minute') or getattr(settings, 'ADMISSION_COMPANY_PER_MINUTE', 60))))
    try:
        for dimension, identity, capacity in dimensions:
            if not controller.consume_tokens(
                scope=f'{scope}:{dimension}',
                identity=identity,
                capacity=capacity,
                refill_per_minute=capacity,
            ):
                raise CapacityRejected(scope=f'{scope}:{dimension}', retry_after_ms=5000)
    except CapacityRejected:
        raise
    except Exception as exc:
        raise CapacityRejected(scope=f'{scope}:coordination', retry_after_ms=2000, overloaded=True) from exc
