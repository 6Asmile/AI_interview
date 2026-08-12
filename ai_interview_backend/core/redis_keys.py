"""Canonical Redis key construction for cache, coordination and realtime data.

Redis is deliberately not a source of business truth.  Keys still need a stable
shape so that operators can reason about ownership, expiry and blast radius.  A
caller must explicitly opt in to opaque parts for user supplied or sensitive
identifiers; those parts are keyed-HMAC digests rather than reversible text.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable
from typing import Final

from django.conf import settings


REDIS_DOMAINS: Final = frozenset({'cache', 'coordination', 'realtime'})
_SAFE_PART = re.compile(r'^[a-z0-9][a-z0-9._-]{0,95}$')


class RedisKeyError(ValueError):
    """Raised when a logical Redis key contains an ambiguous key segment."""


def _plain_part(value: object, *, label: str) -> str:
    text = str(value or '').strip().lower()
    if not _SAFE_PART.fullmatch(text):
        raise RedisKeyError(
            f'{label} must be 1-96 characters using only lowercase letters, '
            'digits, dot, underscore or hyphen'
        )
    return text


def opaque_identifier(value: object, *, purpose: str = 'identifier') -> str:
    """Return a deterministic, non-reversible key part for sensitive input.

    A dedicated secret can be supplied by ``REDIS_KEY_HMAC_SECRET``.  Falling
    back to Django's application secret keeps existing installations working,
    while production can rotate Redis key material independently.
    """

    raw = str(value if value is not None else '')
    if not raw:
        raise RedisKeyError('opaque Redis key parts cannot be empty')
    normalized_purpose = _plain_part(purpose, label='purpose')
    secret = str(getattr(settings, 'REDIS_KEY_HMAC_SECRET', '') or settings.SECRET_KEY)
    message = f'ifaceoff:redis-key:h1:{normalized_purpose}:{raw}'.encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return f'h1_{digest[:40]}'


def build_redis_key(
    *,
    domain: str,
    resource: str,
    tenant: object | None = None,
    version: str = 'v1',
    parts: Iterable[object] = (),
    opaque_parts: Iterable[object] = (),
) -> str:
    """Build ``ifaceoff:{env}:{domain}:{tenant}:{resource}:{version}:...``.

    Plain parts are intentionally strict.  Email addresses, IP addresses,
    access tokens, free-form queries and other sensitive values belong in
    ``opaque_parts`` so they never appear in Redis metadata or monitoring.
    """

    normalized_domain = _plain_part(domain, label='domain')
    if normalized_domain not in REDIS_DOMAINS:
        raise RedisKeyError(f'unsupported Redis domain: {domain!r}')

    environment = _plain_part(getattr(settings, 'IFACEOFF_ENV', 'dev'), label='environment')
    tenant_part = _plain_part('global' if tenant is None else tenant, label='tenant')
    resource_part = _plain_part(resource, label='resource')
    version_part = _plain_part(version, label='version')
    result = [
        'ifaceoff',
        environment,
        normalized_domain,
        tenant_part,
        resource_part,
        version_part,
    ]
    result.extend(_plain_part(part, label='part') for part in parts)
    for index, part in enumerate(opaque_parts):
        result.append(
            opaque_identifier(
                part,
                purpose=f'{normalized_domain}-{resource_part}-{version_part}-{index}',
            )
        )
    return ':'.join(result)
