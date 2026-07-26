from __future__ import annotations

from copy import deepcopy


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
    return config
