import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    configured = str(getattr(settings, 'MODEL_CREDENTIAL_ENCRYPTION_KEY', '') or '').strip()
    if configured:
        key = configured.encode('ascii')
        try:
            Fernet(key)
            return Fernet(key)
        except (ValueError, TypeError):
            pass
    material = str(settings.SECRET_KEY or 'ifaceoff-development-key').encode('utf-8')
    derived = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(derived)


def encrypt_secret(value: str) -> str:
    value = str(value or '').strip()
    if not value:
        return ''
    return _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_secret(value: str) -> str:
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise ValueError('credential_decryption_failed') from exc


def secret_hint(value: str) -> str:
    value = str(value or '')
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:3]}...{value[-4:]}'

