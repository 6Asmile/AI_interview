import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet
from django.conf import settings
from django.core import signing
from django.utils import timezone

from .models import StaffSession


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(f'{settings.SECRET_KEY}:staff-mfa'.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(secret):
    return _fernet().decrypt(secret.encode()).decode()


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def verify_totp(secret, code, window=1):
    value = ''.join(item for item in str(code or '') if item.isdigit())
    if len(value) != 6:
        return False
    padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(time.time()) // 30
    for offset in range(-window, window + 1):
        digest = hmac.new(key, struct.pack('>Q', counter + offset), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        expected = (struct.unpack('>I', digest[index:index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f'{expected:06d}', value):
            return True
    return False


def create_recovery_codes(account, count=10):
    from .models import StaffRecoveryCode
    raw_codes = [f'{secrets.token_hex(3)}-{secrets.token_hex(3)}' for _ in range(count)]
    StaffRecoveryCode.objects.filter(account=account).delete()
    StaffRecoveryCode.objects.bulk_create([
        StaffRecoveryCode(account=account, code_hash=hashlib.sha256(code.encode()).hexdigest())
        for code in raw_codes
    ])
    return raw_codes


def verify_staff_mfa(account, code):
    from .models import StaffRecoveryCode
    device = account.mfa_devices.filter(confirmed_at__isnull=False).first()
    if device and verify_totp(decrypt_secret(device.encrypted_secret), code):
        device.last_used_at = timezone.now()
        device.save(update_fields=['last_used_at'])
        return True
    digest = hashlib.sha256(str(code or '').strip().lower().encode()).hexdigest()
    recovery = StaffRecoveryCode.objects.filter(account=account, code_hash=digest, used_at__isnull=True).first()
    if recovery:
        recovery.used_at = timezone.now()
        recovery.save(update_fields=['used_at'])
        return True
    return False


def totp_uri(account, secret):
    return f'otpauth://totp/{quote("iFaceoff Admin")}:{quote(account.email)}?secret={secret}&issuer={quote("iFaceoff Admin")}'


def challenge_token(account):
    return signing.dumps({'staff_id': str(account.id), 'nonce': secrets.token_hex(12)}, salt='staff-security-setup')


def challenge_account(token, max_age=600):
    from .models import StaffAccount
    payload = signing.loads(token, salt='staff-security-setup', max_age=max_age)
    return StaffAccount.objects.get(pk=payload['staff_id'])


def recovery_confirmation_token(account):
    return signing.dumps(
        {'staff_id': str(account.id), 'purpose': 'recovery-codes-confirmation'},
        salt='staff-recovery-confirmation',
    )


def recovery_confirmation_account(token, max_age=600):
    from .models import StaffAccount
    payload = signing.loads(token, salt='staff-recovery-confirmation', max_age=max_age)
    if payload.get('purpose') != 'recovery-codes-confirmation':
        raise signing.BadSignature('invalid recovery confirmation purpose')
    return StaffAccount.objects.get(pk=payload['staff_id'])


def session_token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_staff_session(account, request):
    raw = secrets.token_urlsafe(48)
    session = StaffSession.objects.create(
        account=account,
        token_hash=session_token_hash(raw),
        ip_address=(request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR') or None),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        mfa_verified_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=int(getattr(settings, 'STAFF_SESSION_HOURS', 8))),
    )
    return raw, session


def set_staff_cookie(response, raw):
    response.set_cookie(
        getattr(settings, 'STAFF_SESSION_COOKIE_NAME', 'ifaceoff_staff_session'), raw,
        max_age=int(getattr(settings, 'STAFF_SESSION_HOURS', 8)) * 3600,
        httponly=True, secure=bool(getattr(settings, 'AUTH_COOKIE_SECURE', not settings.DEBUG)),
        samesite='Strict', path='/api/admin/v1/',
        domain=getattr(settings, 'STAFF_COOKIE_DOMAIN', None) or None,
    )


def clear_staff_cookie(response):
    response.delete_cookie(
        getattr(settings, 'STAFF_SESSION_COOKIE_NAME', 'ifaceoff_staff_session'),
        path='/api/admin/v1/', domain=getattr(settings, 'STAFF_COOKIE_DOMAIN', None) or None,
        samesite='Strict',
    )
