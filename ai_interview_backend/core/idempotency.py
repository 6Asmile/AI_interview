import hashlib
import json
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import IdempotencyRecord


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = '相同幂等键已用于不同请求。'
    default_code = 'idempotency_key_reused'


class OperationInProgress(APIException):
    status_code = 409
    default_code = 'operation_in_progress'

    def __init__(self, operation_id, retry_after_ms=750):
        super().__init__({
            'code': self.default_code,
            'message': '相同操作正在处理中。',
            'retryable': True,
            'retry_after_ms': retry_after_ms,
            'operation_id': str(operation_id),
        })


def request_fingerprint(request) -> str:
    raw = json.dumps(request.data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def run_idempotent(request, scope: str, callback, *, required=True, ttl_hours=24):
    key = str(request.headers.get('Idempotency-Key') or '').strip()
    if required and not key:
        raise ValidationError({'idempotency_key': '请提供 Idempotency-Key 请求头。', 'code': 'idempotency_key_required'})
    if not key:
        return callback()
    if len(key) > 160:
        raise ValidationError({'idempotency_key': 'Idempotency-Key 不能超过 160 个字符。'})
    fingerprint = request_fingerprint(request)
    now = timezone.now()
    claim_token = uuid.uuid4()
    lease_expires_at = now + timedelta(minutes=5)

    try:
        with transaction.atomic():
            try:
                record = IdempotencyRecord.objects.select_for_update().get(
                    user=request.user,
                    scope=scope,
                    key=key,
                )
                created = False
            except IdempotencyRecord.DoesNotExist:
                try:
                    with transaction.atomic():
                        record = IdempotencyRecord.objects.create(
                            user=request.user,
                            scope=scope,
                            key=key,
                            request_hash=fingerprint,
                            status=IdempotencyRecord.Status.PENDING,
                            claim_token=claim_token,
                            lease_expires_at=lease_expires_at,
                            expires_at=now + timedelta(hours=ttl_hours),
                        )
                    created = True
                except IntegrityError:
                    record = IdempotencyRecord.objects.select_for_update().get(
                        user=request.user,
                        scope=scope,
                        key=key,
                    )
                    created = False

            if not created:
                if record.request_hash != fingerprint:
                    raise IdempotencyConflict()
                if record.status == IdempotencyRecord.Status.COMPLETED:
                    response = Response(record.response_body, status=record.response_status)
                    response['X-Idempotent-Replay'] = 'true'
                    response['X-Operation-Id'] = str(record.operation_id)
                    return response
                lease_active = record.lease_expires_at and record.lease_expires_at > now
                if record.status == IdempotencyRecord.Status.PENDING and lease_active:
                    raise OperationInProgress(record.operation_id)
                record.status = IdempotencyRecord.Status.PENDING
                record.claim_token = claim_token
                record.lease_expires_at = lease_expires_at
                record.error_code = ''
                record.expires_at = now + timedelta(hours=ttl_hours)
                record.save(update_fields=[
                    'status', 'claim_token', 'lease_expires_at', 'error_code', 'expires_at', 'updated_at',
                ])

        response = callback()
        if not isinstance(response, Response) or getattr(response, 'streaming', False):
            IdempotencyRecord.objects.filter(id=record.id, claim_token=claim_token).update(
                status=IdempotencyRecord.Status.FAILED,
                error_code='unsupported_idempotent_response',
                lease_expires_at=None,
                updated_at=timezone.now(),
            )
            return response
        response_data = _json_safe(
            response.data if isinstance(response.data, (dict, list)) else {'result': response.data}
        )
        retryable = bool(response_data.get('retryable')) if isinstance(response_data, dict) else False
        if response.status_code >= 500 or retryable:
            IdempotencyRecord.objects.filter(id=record.id, claim_token=claim_token).update(
                status=IdempotencyRecord.Status.FAILED,
                error_code=str(response_data.get('code') or f'http_{response.status_code}')[:120],
                lease_expires_at=None,
                updated_at=timezone.now(),
            )
            response['X-Operation-Id'] = str(record.operation_id)
            return response
        IdempotencyRecord.objects.filter(id=record.id, claim_token=claim_token).update(
            status=IdempotencyRecord.Status.COMPLETED,
            response_status=response.status_code,
            response_body=response_data,
            lease_expires_at=None,
            updated_at=timezone.now(),
        )
        response['X-Operation-Id'] = str(record.operation_id)
    except Exception as exc:
        IdempotencyRecord.objects.filter(
            user=request.user,
            scope=scope,
            key=key,
            claim_token=claim_token,
        ).update(
            status=IdempotencyRecord.Status.FAILED,
            error_code=type(exc).__name__,
            lease_expires_at=None,
            updated_at=timezone.now(),
        )
        raise
    return response
