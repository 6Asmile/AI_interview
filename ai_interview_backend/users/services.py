import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django_redis import get_redis_connection


def generate_email_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _code_hmac(email: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f'{email.strip().lower()}:{code}'.encode(), hashlib.sha256).hexdigest()


def email_code_key(email: str) -> str:
    return f'ifaceoff:{getattr(settings, "IFACEOFF_ENV", "dev")}:coordination:auth:email-code:{_email_digest(email)}'


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
    redis.hset(key, mapping={
        'code_hmac': _code_hmac(normalized_email, code),
        'attempts': 0,
    })
    redis.expire(key, 300)

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
        redis.delete(key)
        return False
