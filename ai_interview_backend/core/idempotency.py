import hashlib
import json
import re
import time
import uuid
from contextvars import ContextVar
from datetime import timedelta

from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import IdempotencyRecord


_current_idempotency_record_id = ContextVar('current_idempotency_record_id', default=None)


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = '相同幂等键已用于不同请求。'
    default_code = 'idempotency_key_reused'


class OperationInProgress(APIException):
    status_code = 409
    default_code = 'operation_in_progress'

    def __init__(self, operation_id, retry_after_ms=750):
        detail = {
            'code': self.default_code,
            'message': '相同操作正在处理中。',
            'retryable': True,
            'retry_after_ms': retry_after_ms,
        }
        if operation_id:
            detail['operation_id'] = str(operation_id)
        super().__init__(detail)


def _public_operation_id(record: IdempotencyRecord):
    return record.operation_id


def bind_current_operation(operation) -> bool:
    """Bind an operation created inside the active idempotent callback."""

    record_id = _current_idempotency_record_id.get()
    if not record_id:
        return False
    with transaction.atomic():
        record = IdempotencyRecord.objects.select_for_update().filter(pk=record_id).first()
        if not record:
            return False
        key_hash = hashlib.sha256(record.key.encode('utf-8')).hexdigest()
        if not operation.idempotency_key_hash:
            operation.idempotency_key_hash = key_hash
            operation.save(update_fields=['idempotency_key_hash', 'updated_at'])
        if record.operation_id and record.operation_id != operation.id:
            raise IdempotencyConflict('幂等请求已绑定其他异步操作。')
        record.operation = operation
        record.save(update_fields=['operation', 'updated_at'])
    return True


def _normalize_fingerprint_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, 'name') and hasattr(value, 'size') and hasattr(value, 'read'):
        return {
            'upload_name': str(value.name),
            'upload_size': int(value.size),
            'content_type': str(getattr(value, 'content_type', '') or ''),
        }
    if hasattr(value, 'lists'):
        return {
            str(key): [_normalize_fingerprint_value(item) for item in values]
            for key, values in sorted(value.lists(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, dict):
        return {
            str(key): _normalize_fingerprint_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_fingerprint_value(item) for item in value]
    return str(value)


def _uploaded_file_checksum(upload) -> str:
    digest = hashlib.sha256()
    try:
        original_position = upload.tell()
    except (AttributeError, OSError):
        original_position = None
    try:
        if hasattr(upload, 'chunks'):
            for chunk in upload.chunks():
                digest.update(chunk)
        else:
            while True:
                chunk = upload.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    finally:
        try:
            upload.seek(original_position if original_position is not None else 0)
        except (AttributeError, OSError):
            pass
    return digest.hexdigest()


def _uploaded_files_fingerprint(request):
    files = getattr(request, 'FILES', None)
    if not files:
        return {}
    if hasattr(files, 'lists'):
        file_items = files.lists()
    else:
        file_items = (
            (key, value if isinstance(value, list) else [value])
            for key, value in files.items()
        )
    return {
        str(field): [
            {
                'name': str(upload.name),
                'size': int(upload.size),
                'content_type': str(getattr(upload, 'content_type', '') or ''),
                'sha256': _uploaded_file_checksum(upload),
            }
            for upload in uploads
        ]
        for field, uploads in sorted(file_items, key=lambda pair: str(pair[0]))
    }


def request_fingerprint(request, scope: str = '') -> str:
    path = str(getattr(request, 'path_info', '') or getattr(request, 'path', '') or '/')
    path = re.sub(r'/+', '/', f'/{path.lstrip("/")}')
    if len(path) > 1:
        path = path.rstrip('/')
    data = getattr(request, 'data', {}) or {}
    headers = getattr(request, 'headers', {}) or {}
    operation_reason = str(headers.get('Operation-Reason') or '')
    if hasattr(data, 'get'):
        operation_reason = str(
            data.get('operation_reason')
            or operation_reason
        )
    canonical = {
        'method': str(getattr(request, 'method', 'POST') or 'POST').upper(),
        'path': path,
        'scope': str(scope or ''),
        'operation_reason': operation_reason,
        'data': _normalize_fingerprint_value(data),
        'files': _uploaded_files_fingerprint(request),
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _claim_record(*, user, scope, key, fingerprint, now, claim_token, lease_expires_at, ttl_hours):
    with transaction.atomic():
        try:
            record = IdempotencyRecord.objects.select_for_update().get(
                user=user,
                scope=scope,
                key=key,
            )
            created = False
        except IdempotencyRecord.DoesNotExist:
            try:
                with transaction.atomic():
                    record = IdempotencyRecord.objects.create(
                        user=user,
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
                    user=user,
                    scope=scope,
                    key=key,
                )
                created = False

        if not created:
            expired = record.expires_at <= now
            if not expired and record.request_hash != fingerprint:
                raise IdempotencyConflict()
            if not expired and record.status == IdempotencyRecord.Status.COMPLETED:
                response = Response(record.response_body, status=record.response_status)
                response['X-Idempotent-Replay'] = 'true'
                if _public_operation_id(record):
                    response['X-Operation-Id'] = str(_public_operation_id(record))
                return record, response
            lease_active = not expired and record.lease_expires_at and record.lease_expires_at > now
            if record.status == IdempotencyRecord.Status.PENDING and lease_active:
                raise OperationInProgress(_public_operation_id(record))
            record.status = IdempotencyRecord.Status.PENDING
            record.request_hash = fingerprint
            record.claim_token = claim_token
            record.lease_expires_at = lease_expires_at
            record.error_code = ''
            record.response_status = 200
            record.response_body = {}
            if expired:
                record.operation = None
            record.expires_at = now + timedelta(hours=ttl_hours)
            record.save(update_fields=[
                'status', 'request_hash', 'claim_token', 'lease_expires_at', 'error_code',
                'response_status', 'response_body', 'operation', 'expires_at', 'updated_at',
            ])
        return record, None


def run_idempotent(request, scope: str, callback, *, required=True, ttl_hours=24):
    key = str(request.headers.get('Idempotency-Key') or '').strip()
    if required and not key:
        raise ValidationError({'idempotency_key': '请提供 Idempotency-Key 请求头。', 'code': 'idempotency_key_required'})
    if not key:
        return callback()
    if len(key) > 160:
        raise ValidationError({'idempotency_key': 'Idempotency-Key 不能超过 160 个字符。'})
    fingerprint = request_fingerprint(request, scope)
    now = timezone.now()
    claim_token = uuid.uuid4()
    lease_expires_at = now + timedelta(minutes=5)

    try:
        claim_attempt = 0
        while True:
            try:
                record, replay_response = _claim_record(
                    user=request.user,
                    scope=scope,
                    key=key,
                    fingerprint=fingerprint,
                    now=now,
                    claim_token=claim_token,
                    lease_expires_at=lease_expires_at,
                    ttl_hours=ttl_hours,
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

        context_token = _current_idempotency_record_id.set(record.id)
        try:
            response = callback()
        finally:
            _current_idempotency_record_id.reset(context_token)
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
        if isinstance(response_data, dict) and response_data.get('operation_id'):
            from .models import AsyncOperation
            operation = AsyncOperation.objects.filter(
                pk=response_data['operation_id'],
                user=request.user,
            ).first()
            if operation:
                with transaction.atomic():
                    locked_record = IdempotencyRecord.objects.select_for_update().get(pk=record.pk)
                    if locked_record.operation_id and locked_record.operation_id != operation.id:
                        raise IdempotencyConflict('幂等请求已绑定其他异步操作。')
                    locked_record.operation = operation
                    locked_record.save(update_fields=['operation', 'updated_at'])
                    record.operation = operation
        retryable = bool(response_data.get('retryable')) if isinstance(response_data, dict) else False
        if response.status_code >= 500 or retryable:
            IdempotencyRecord.objects.filter(id=record.id, claim_token=claim_token).update(
                status=IdempotencyRecord.Status.FAILED,
                error_code=str(response_data.get('code') or f'http_{response.status_code}')[:120],
                lease_expires_at=None,
                updated_at=timezone.now(),
            )
            record.refresh_from_db(fields=['operation'])
            if _public_operation_id(record):
                response['X-Operation-Id'] = str(_public_operation_id(record))
            return response
        IdempotencyRecord.objects.filter(id=record.id, claim_token=claim_token).update(
            status=IdempotencyRecord.Status.COMPLETED,
            response_status=response.status_code,
            response_body=response_data,
            lease_expires_at=None,
            updated_at=timezone.now(),
        )
        record.refresh_from_db(fields=['operation'])
        if _public_operation_id(record):
            response['X-Operation-Id'] = str(_public_operation_id(record))
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
