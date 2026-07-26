from __future__ import annotations

import hashlib
import secrets
from copy import deepcopy

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .models import ResumeShareAccess, ResumeShareLink
from .rendering import artifact_cache_key
from .schema import sha256_json, strip_internal_metadata
from .templates import design_hash


PRIVATE_FIELDS = {
    'email': ('basics', 'email'),
    'phone': ('basics', 'phone'),
    'address': ('basics', 'location', 'address'),
    'image': ('basics', 'image'),
}
DEFAULT_FIELD_POLICY = {field: False for field in PRIVATE_FIELDS}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if value else ''


def redact_shared_resume(
    payload: dict,
    policy: dict | None = None,
    *,
    preserve_asset_references: bool = False,
) -> dict:
    data = strip_internal_metadata(payload, preserve_asset_references=preserve_asset_references)
    effective = {**DEFAULT_FIELD_POLICY, **(policy or {})}
    for name, path in PRIVATE_FIELDS.items():
        if effective.get(name) is True:
            continue
        target = data
        for part in path[:-1]:
            target = target.get(part) if isinstance(target, dict) else None
            if not isinstance(target, dict):
                break
        if isinstance(target, dict):
            target.pop(path[-1], None)
    return data


def shared_render_snapshot(*, resume, content_version, design_revision, field_policy):
    resume_json = redact_shared_resume(
        content_version.resume_json,
        field_policy,
        preserve_asset_references=True,
    )
    design_json = deepcopy(design_revision.design_json)
    if not (field_policy or {}).get('image', False):
        design_json['show_avatar'] = False
    key = artifact_cache_key(
        sha256_json(resume_json),
        design_hash(design_json),
        'pdf',
        namespace=f'resume:{resume.pk}:share',
    )
    return resume_json, design_json, key


def create_share_link(*, resume, content_version, design_revision, user, password='', field_policy=None,
                      expires_at=None, allow_download=False, download_limit=None):
    raw_token = secrets.token_urlsafe(32)
    link = ResumeShareLink.objects.create(
        resume=resume,
        content_version=content_version,
        design_revision=design_revision,
        token_hash=token_hash(raw_token),
        token_hint=raw_token[-8:],
        password_hash=make_password(password) if password else '',
        field_policy={**DEFAULT_FIELD_POLICY, **(field_policy or {})},
        expires_at=expires_at,
        allow_download=allow_download,
        download_limit=download_limit,
        created_by=user,
    )
    return link, raw_token


def resolve_share(
    *,
    token: str,
    password: str = '',
    request=None,
    action=ResumeShareAccess.Action.VIEW,
    consume_download=True,
):
    link = ResumeShareLink.objects.select_related(
        'resume', 'content_version', 'design_revision',
    ).filter(token_hash=token_hash(token)).first()
    metadata = {}
    if not link:
        raise PermissionDenied('分享链接不存在或已失效。')
    now = timezone.now()
    denied_reason = ''
    if link.revoked_at:
        denied_reason = 'revoked'
    elif link.expires_at and link.expires_at <= now:
        denied_reason = 'expired'
    elif link.password_hash and not check_password(password, link.password_hash):
        denied_reason = 'password'
    elif action == ResumeShareAccess.Action.DOWNLOAD and not link.allow_download:
        denied_reason = 'download_disabled'
    elif (
        action == ResumeShareAccess.Action.DOWNLOAD
        and link.download_limit is not None
        and link.download_count >= link.download_limit
    ):
        denied_reason = 'download_limit'
    if denied_reason:
        metadata['reason'] = denied_reason
        record_share_access(link, request, ResumeShareAccess.Action.DENIED, metadata)
        if denied_reason == 'password':
            raise AuthenticationFailed('分享密码错误。')
        raise PermissionDenied('分享链接不可用。')
    if action == ResumeShareAccess.Action.DOWNLOAD and consume_download:
        with transaction.atomic():
            locked = ResumeShareLink.objects.select_for_update().get(pk=link.pk)
            if locked.download_limit is not None and locked.download_count >= locked.download_limit:
                raise PermissionDenied('下载次数已用尽。')
            locked.download_count += 1
            locked.save(update_fields=['download_count'])
    if action != ResumeShareAccess.Action.DOWNLOAD or consume_download:
        record_share_access(link, request, action, metadata)
    return link


def record_share_access(link, request, action, metadata=None):
    ip = request.META.get('REMOTE_ADDR', '') if request else ''
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
    ResumeShareAccess.objects.create(
        share_link=link,
        action=action,
        ip_hash=_fingerprint(ip),
        user_agent_hash=_fingerprint(user_agent),
        metadata=metadata or {},
    )
