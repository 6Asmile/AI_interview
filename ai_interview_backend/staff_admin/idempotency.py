import hashlib
import json
import time
import uuid
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import AdminIdempotencyRecord


class StaffIdempotencyConflict(APIException):
    status_code = 409
    default_detail = '相同幂等键已用于不同的管理端请求。'
    default_code = 'staff_idempotency_key_reused'


class StaffOperationInProgress(APIException):
    status_code = 409
    default_code = 'staff_operation_in_progress'

    def __init__(self, operation_id=None, retry_after_ms=750):
        detail = {
            'code': self.default_code,
            'message': '相同管理操作正在处理中。',
            'retryable': True,
            'retry_after_ms': retry_after_ms,
        }
        if operation_id:
            detail['operation_id'] = str(operation_id)
        super().__init__(detail)


_META_KEY = '_ifaceoff_idempotency'


def _fingerprint(request):
    raw = json.dumps(request.data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _json_safe(value):
    """Normalize DRF response data before storing it in a JSONField."""

    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False))


def _authoritative_operation_id(response_body):
    """Return only a real platform Operation UUID exposed by the callback."""

    if not isinstance(response_body, dict):
        return None
    raw = response_body.get('operation_id')
    if not raw:
        return None
    try:
        return str(uuid.UUID(str(raw)))
    except (TypeError, ValueError, AttributeError):
        return None


def _claim_body(*, status, claim_token, lease_expires_at=None, error_code=''):
    return {
        _META_KEY: {
            'version': 1,
            'status': status,
            'claim_token': str(claim_token),
            'lease_expires_at': lease_expires_at.isoformat() if lease_expires_at else '',
            'error_code': str(error_code)[:120],
        }
    }


def _claim_metadata(record):
    body = record.response_body if isinstance(record.response_body, dict) else {}
    metadata = body.get(_META_KEY)
    return metadata if isinstance(metadata, dict) and metadata.get('version') == 1 else None


def _lease_is_active(metadata, now):
    if not metadata or metadata.get('status') != 'pending':
        return False
    parsed = parse_datetime(str(metadata.get('lease_expires_at') or ''))
    return bool(parsed and parsed > now)


def _create_claim(*, account, scope, key, fingerprint, claim_token, lease_expires_at, expires_at):
    return AdminIdempotencyRecord.objects.create(
        account=account,
        scope=scope,
        key=key,
        request_hash=fingerprint,
        response_status=102,
        response_body=_claim_body(
            status='pending',
            claim_token=claim_token,
            lease_expires_at=lease_expires_at,
        ),
        expires_at=expires_at,
    )


def _claim_record(*, account, scope, key, fingerprint, now, claim_token, lease_expires_at, expires_at):
    with transaction.atomic():
        try:
            record = AdminIdempotencyRecord.objects.select_for_update().get(
                account=account,
                scope=scope,
                key=key,
            )
            created = False
        except AdminIdempotencyRecord.DoesNotExist:
            try:
                with transaction.atomic():
                    record = _create_claim(
                        account=account,
                        scope=scope,
                        key=key,
                        fingerprint=fingerprint,
                        claim_token=claim_token,
                        lease_expires_at=lease_expires_at,
                        expires_at=expires_at,
                    )
                created = True
            except IntegrityError:
                record = AdminIdempotencyRecord.objects.select_for_update().get(
                    account=account,
                    scope=scope,
                    key=key,
                )
                created = False

        if not created and record.expires_at <= now:
            # Expiration ends the key's conflict/replay window.  Replacing the
            # row also gives the new operation a fresh public operation ID.
            record.delete()
            record = _create_claim(
                account=account,
                scope=scope,
                key=key,
                fingerprint=fingerprint,
                claim_token=claim_token,
                lease_expires_at=lease_expires_at,
                expires_at=expires_at,
            )
            created = True

        if created:
            return record, None
        if record.request_hash != fingerprint:
            raise StaffIdempotencyConflict()

        metadata = _claim_metadata(record)
        if _lease_is_active(metadata, now):
            # AdminIdempotencyRecord.id is a claim identity, not a platform
            # Operation UUID. Do not expose it as a fake public operation.
            raise StaffOperationInProgress()
        if not metadata:
            response = Response(record.response_body, status=record.response_status)
            response['X-Idempotent-Replay'] = 'true'
            operation_id = _authoritative_operation_id(record.response_body)
            if operation_id:
                response['X-Operation-Id'] = operation_id
            return record, response

        record.response_status = 102
        record.response_body = _claim_body(
            status='pending',
            claim_token=claim_token,
            lease_expires_at=lease_expires_at,
        )
        record.expires_at = expires_at
        record.save(update_fields=['response_status', 'response_body', 'expires_at'])
        return record, None


def _finish_claim(record_id, claim_token, *, response_status, response_body):
    """Finish only the claim still owned by ``claim_token``."""

    with transaction.atomic():
        try:
            record = AdminIdempotencyRecord.objects.select_for_update().get(pk=record_id)
        except AdminIdempotencyRecord.DoesNotExist:
            return False
        metadata = _claim_metadata(record)
        if not metadata or metadata.get('claim_token') != str(claim_token):
            return False
        record.response_status = response_status
        record.response_body = response_body
        record.save(update_fields=['response_status', 'response_body'])
        return True


def run_staff_idempotent(request, scope, callback, *, ttl_hours=24):
    key = str(request.headers.get('Idempotency-Key') or '').strip()
    if not key:
        raise ValidationError({'idempotency_key': '请提供 Idempotency-Key 请求头。', 'code': 'idempotency_key_required'})
    if len(key) > 160:
        raise ValidationError({'idempotency_key': 'Idempotency-Key 不能超过 160 个字符。'})
    if isinstance(ttl_hours, bool) or type(ttl_hours) is not int or not 1 <= ttl_hours <= 24 * 30:
        raise ValueError('ttl_hours must be an integer between 1 and 720')

    fingerprint = _fingerprint(request)
    claim_token = uuid.uuid4()
    claim_attempt = 0
    while True:
        now = timezone.now()
        try:
            record, replay_response = _claim_record(
                account=request.user,
                scope=scope,
                key=key,
                fingerprint=fingerprint,
                now=now,
                claim_token=claim_token,
                lease_expires_at=now + timedelta(minutes=5),
                expires_at=now + timedelta(hours=ttl_hours),
            )
            if replay_response:
                return replay_response
            break
        except OperationalError as exc:
            is_sqlite_lock = connection.vendor == 'sqlite' and 'locked' in str(exc).lower()
            claim_attempt += 1
            if not is_sqlite_lock or claim_attempt >= 50:
                raise
            time.sleep(min(0.1, 0.005 * claim_attempt))

    try:
        response = callback()
        if not isinstance(response, Response) or getattr(response, 'streaming', False):
            _finish_claim(
                record.id,
                claim_token,
                response_status=500,
                response_body=_claim_body(
                    status='failed',
                    claim_token=claim_token,
                    error_code='unsupported_idempotent_response',
                ),
            )
            return response

        response_data = _json_safe(
            response.data if isinstance(response.data, (dict, list)) else {'result': response.data}
        )
        retryable = bool(response_data.get('retryable')) if isinstance(response_data, dict) else False
        if response.status_code >= 500 or retryable:
            stored_body = _claim_body(
                status='failed',
                claim_token=claim_token,
                error_code=(
                    response_data.get('code') if isinstance(response_data, dict) else ''
                ) or f'http_{response.status_code}',
            )
        else:
            stored_body = response_data
        _finish_claim(
            record.id,
            claim_token,
            response_status=response.status_code,
            response_body=stored_body,
        )
        operation_id = _authoritative_operation_id(response_data)
        if operation_id:
            response['X-Operation-Id'] = operation_id
        return response
    except Exception as exc:
        _finish_claim(
            record.id,
            claim_token,
            response_status=500,
            response_body=_claim_body(
                status='failed',
                claim_token=claim_token,
                error_code=type(exc).__name__,
            ),
        )
        raise
