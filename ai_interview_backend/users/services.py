import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django_redis import get_redis_connection

from core.redis_keys import build_redis_key


def generate_email_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _code_hmac(email: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f'{email.strip().lower()}:{code}'.encode(), hashlib.sha256).hexdigest()


def email_code_key(email: str) -> str:
    return build_redis_key(
        domain='coordination',
        resource='email-verification',
        parts=('registration',),
        opaque_parts=(email.strip().lower(),),
    )


_STORE_CODE_SCRIPT = """
redis.call(
  'HSET', KEYS[1],
  'code_hmac', ARGV[1],
  'attempts', 0,
  'generation', ARGV[2]
)
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[3]))
return ARGV[2]
"""

_DELETE_GENERATION_SCRIPT = """
if redis.call('HGET', KEYS[1], 'generation') == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


_VERIFY_SCRIPT = """
local key = KEYS[1]
local expected = ARGV[1]
local max_attempts = tonumber(ARGV[2])
if redis.call('EXISTS', key) == 0 then return -1 end
local attempts = tonumber(redis.call('HGET', key, 'attempts') or '0')
if attempts >= max_attempts then
  redis.call('DEL', key)
  return -2
end
local actual = redis.call('HGET', key, 'code_hmac')
if actual ~= expected then
  attempts = redis.call('HINCRBY', key, 'attempts', 1)
  if attempts >= max_attempts then redis.call('DEL', key) end
  return 0
end
redis.call('DEL', key)
return 1
"""


def verify_email_code(email: str, code: str) -> str:
    redis = get_redis_connection('coordination')
    result = int(redis.eval(_VERIFY_SCRIPT, 1, email_code_key(email), _code_hmac(email, code), 5))
    return {1: 'ok', 0: 'invalid', -1: 'expired', -2: 'locked'}.get(result, 'invalid')


def send_verification_code(email: str) -> bool:
    """
    生成验证码，存入Redis，并发送邮件。
    """
    normalized_email = email.strip().lower()
    code = generate_email_code()
    redis = get_redis_connection('coordination')
    key = email_code_key(normalized_email)
    generation = secrets.token_urlsafe(18)
    ttl_seconds = max(
        60,
        min(900, int(getattr(settings, 'EMAIL_VERIFICATION_CODE_TTL_SECONDS', 300))),
    )
    # HSET and TTL are one Redis operation.  The generation token ensures that
    # a failed, slower resend cannot delete a newer code issued concurrently.
    redis.eval(
        _STORE_CODE_SCRIPT,
        1,
        key,
        _code_hmac(normalized_email, code),
        generation,
        ttl_seconds * 1000,
    )

    # 【核心修正】
    subject = '【IFaceOff】您的注册验证码'
    message = f'您好！\n\n您的注册验证码是：{code}\n\n该验证码5分钟内有效，请勿泄露给他人。\n\n感谢您使用 IFaceOff 智能面试平台！'

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [normalized_email],
            fail_silently=False,
        )
        return True
    except Exception:
        try:
            redis.eval(_DELETE_GENERATION_SCRIPT, 1, key, generation)
        except Exception:
            pass
        return False
