from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar


_policy_scope = ContextVar('resume_creation_policy_scope', default=None)


@contextmanager
def resume_runtime_policy_scope():
    """One policy read per creation; no process-wide cache or stale next request."""
    if _policy_scope.get() is not None:
        yield
        return
    token = _policy_scope.set({})
    try:
        yield
    finally:
        _policy_scope.reset(token)


DEFAULT_RESUME_RUNTIME_CONFIG = {
    'enabled_templates': [
        'ats-classic',
        'modern-professional',
        'engineering',
        'graduate',
        'management-consulting',
        'academic-research',
    ],
    'renderer_version': '2.8',
    'ats_rules_version': '1.0.0',
    'render_timeout_seconds': 20,
    'max_input_bytes': 2_000_000,
}


def resume_runtime_config() -> dict:
    """Return the deployed, validated control-plane policy without exposing resume data."""
    scope = _policy_scope.get()
    if scope is not None and 'config' in scope:
        return deepcopy(scope['config'])
    config = deepcopy(DEFAULT_RESUME_RUNTIME_CONFIG)
    try:
        from core.models import RuntimePolicy
        policy = RuntimePolicy.objects.filter(key='resume-config', enabled=True).first()
    except Exception:
        policy = None
    if policy and isinstance(policy.config, dict):
        config.update({
            key: value
            for key, value in policy.config.items()
            if key in DEFAULT_RESUME_RUNTIME_CONFIG
        })
    if scope is not None:
        scope['config'] = deepcopy(config)
    return config
