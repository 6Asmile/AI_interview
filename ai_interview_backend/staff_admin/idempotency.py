import hashlib
import json
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import AdminIdempotencyRecord


class StaffIdempotencyConflict(APIException):
    status_code = 409
    default_detail = '相同幂等键已用于不同的管理端请求。'
    default_code = 'staff_idempotency_key_reused'


def _fingerprint(request):
    raw = json.dumps(request.data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _json_safe(value):
    """Normalize DRF response data before storing it in a JSONField."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False))


def run_staff_idempotent(request, scope, callback, *, ttl_hours=24):
    key = str(request.headers.get('Idempotency-Key') or '').strip()
    if not key:
        raise ValidationError({'idempotency_key': '请提供 Idempotency-Key 请求头。', 'code': 'idempotency_key_required'})
    if len(key) > 160:
        raise ValidationError({'idempotency_key': 'Idempotency-Key 不能超过 160 个字符。'})
    fingerprint = _fingerprint(request)
    existing = AdminIdempotencyRecord.objects.filter(account=request.user, scope=scope, key=key).first()
    if existing:
        if existing.request_hash != fingerprint:
            raise StaffIdempotencyConflict()
        response = Response(existing.response_body, status=existing.response_status)
        response['X-Idempotent-Replay'] = 'true'
        return response
    response = callback()
    if not isinstance(response, Response) or getattr(response, 'streaming', False):
        return response
    try:
        with transaction.atomic():
            AdminIdempotencyRecord.objects.create(
                account=request.user,
                scope=scope,
                key=key,
                request_hash=fingerprint,
                response_status=response.status_code,
                response_body=_json_safe(
                    response.data if isinstance(response.data, (dict, list)) else {'result': response.data}
                ),
                expires_at=timezone.now() + timedelta(hours=ttl_hours),
            )
    except IntegrityError:
        stored = AdminIdempotencyRecord.objects.get(account=request.user, scope=scope, key=key)
        if stored.request_hash != fingerprint:
            raise StaffIdempotencyConflict()
    return response
