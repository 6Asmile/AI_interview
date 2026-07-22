from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from django.core.cache import caches
from django_redis import get_redis_connection


@dataclass(frozen=True)
class CachePolicy:
    ttl_seconds: int
    soft_ttl_seconds: int
    negative_ttl_seconds: int = 45
    jitter_ratio: float = 0.2
    lock_ttl_seconds: int = 30
    lock_wait_seconds: float = 0.25
    allow_stale: bool = True


class CacheRebuildInProgress(RuntimeError):
    pass


POLICIES = {
    'article_recommendations': CachePolicy(86400, 3600, negative_ttl_seconds=60),
    'reference_answer': CachePolicy(3600, 1800, negative_ttl_seconds=30, lock_ttl_seconds=120),
    'model_catalog': CachePolicy(900, 300, negative_ttl_seconds=30),
    'public_knowledge': CachePolicy(1800, 600, negative_ttl_seconds=45),
}


def jittered_ttl(policy: CachePolicy) -> int:
    spread = max(1, int(policy.ttl_seconds * policy.jitter_ratio))
    return max(policy.soft_ttl_seconds + 1, policy.ttl_seconds + random.randint(-spread, spread))


def _metric(name: str) -> None:
    try:
        get_redis_connection('default').incr(f'ifaceoff:cache-metric:{name}')
    except Exception:
        pass


def set_policy_value(key: str, value: Any, policy_name: str, *, alias='default') -> None:
    policy = POLICIES[policy_name]
    hard_ttl = jittered_ttl(policy)
    caches[alias].set(key, {
        '_ifaceoff_cache_envelope': 1,
        'value': value,
        'negative': value is None,
        'soft_expires_at': time.time() + policy.soft_ttl_seconds,
    }, timeout=policy.negative_ttl_seconds if value is None else hard_ttl)


def get_or_load(
    key: str,
    loader: Callable[[], Any],
    policy_name: str,
    *,
    alias='default',
) -> tuple[Any, str]:
    """Cache-aside with negative caching, TTL jitter and Redis single-flight."""

    policy = POLICIES[policy_name]
    cache = caches[alias]
    try:
        envelope = cache.get(key)
    except Exception:
        _metric(f'{policy_name}:redis_error')
        return loader(), 'source'
    stale = None
    if isinstance(envelope, dict) and envelope.get('_ifaceoff_cache_envelope') == 1:
        if envelope.get('negative'):
            _metric(f'{policy_name}:negative_hit')
            return None, 'negative_cache'
        if float(envelope.get('soft_expires_at') or 0) > time.time():
            _metric(f'{policy_name}:hit')
            return envelope.get('value'), 'cache'
        stale = envelope.get('value')

    _metric(f'{policy_name}:miss')
    try:
        redis = get_redis_connection(alias)
        lock = redis.lock(
            f'ifaceoff:singleflight:{key}',
            timeout=policy.lock_ttl_seconds,
            blocking_timeout=policy.lock_wait_seconds,
        )
        acquired = lock.acquire(blocking=True)
    except Exception:
        acquired = False
        lock = None

    if not acquired:
        _metric(f'{policy_name}:singleflight_wait')
        if stale is not None and policy.allow_stale:
            return stale, 'stale'
        try:
            refreshed = cache.get(key)
            if isinstance(refreshed, dict) and refreshed.get('_ifaceoff_cache_envelope') == 1:
                return refreshed.get('value'), 'cache_after_wait'
        except Exception:
            pass
        raise CacheRebuildInProgress(key)

    try:
        refreshed = cache.get(key)
        if isinstance(refreshed, dict) and refreshed.get('_ifaceoff_cache_envelope') == 1:
            if float(refreshed.get('soft_expires_at') or 0) > time.time():
                return refreshed.get('value'), 'cache_after_lock'
        value = loader()
        set_policy_value(key, value, policy_name, alias=alias)
        _metric(f'{policy_name}:rebuilt')
        return value, 'source'
    finally:
        try:
            if lock and lock.owned():
                lock.release()
        except Exception:
            pass
