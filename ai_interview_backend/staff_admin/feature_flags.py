import hashlib

from .models import PlatformFeatureFlag


def feature_flag_enabled(key: str, *, subject=None, default: bool = False) -> bool:
    """Evaluate an existing platform flag with deterministic percentage rollout."""
    try:
        flag = PlatformFeatureFlag.objects.filter(key=key).first()
    except Exception:
        return default
    if not flag:
        return default
    if not flag.enabled:
        return False
    audience = flag.audience or {}
    subject_id = str(getattr(subject, 'id', '') or '')
    included_ids = {str(item) for item in audience.get('user_ids') or []}
    excluded_ids = {str(item) for item in audience.get('excluded_user_ids') or []}
    if subject_id in excluded_ids:
        return False
    if included_ids and subject_id not in included_ids:
        return False
    percentage = max(0, min(100, int(flag.rollout_percentage or 0)))
    if percentage >= 100:
        return True
    if percentage <= 0 or not subject_id:
        return False
    bucket = int(hashlib.sha256(f'{flag.key}:{flag.version}:{subject_id}'.encode()).hexdigest()[:8], 16) % 100
    return bucket < percentage
