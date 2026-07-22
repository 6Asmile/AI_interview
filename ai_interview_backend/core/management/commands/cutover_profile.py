from __future__ import annotations

import hashlib

from django.apps import apps
from django.core import serializers


TRANSIENT_MODELS = {
    'admin.logentry',
    'blog.dailypoststats',
    'chat.chatoutbox',
    'contenttypes.contenttype',
    'core.asyncoperation',
    'core.idempotencyrecord',
    'interviews.interviewagentmemoryevent',
    'interviews.interviewagentnoderun',
    'interviews.interviewagentrun',
    'interviews.interviewagenttoolcall',
    'interviews.interviewagenttrace',
    'interviews.interviewquestiongenerationjob',
    'notifications.notificationoutbox',
    'sessions.session',
    'system.modelrequestledger',
    'token_blacklist.blacklistedtoken',
    'token_blacklist.outstandingtoken',
    'users.authsession',
    'users.oauthflow',
    'video_uploads.filechunk',
}


def included_models(include_runtime: bool = False):
    excluded = set() if include_runtime else TRANSIENT_MODELS
    return [
        model
        for model in apps.get_models()
        if model._meta.managed
        and not model._meta.proxy
        and model._meta.label_lower not in excluded
        and model._meta.label_lower != 'auth.permission'
    ]


def model_digest(model) -> tuple[int, str]:
    queryset = model._default_manager.order_by(model._meta.pk.name)
    payload = serializers.serialize(
        'json',
        queryset.iterator(chunk_size=500),
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )
    return queryset.count(), hashlib.sha256(payload.encode('utf-8')).hexdigest()
