# users/services.py
import random
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache


def generate_email_code() -> str:
    """生成一个6位的随机数字验证码"""
    return str(random.randint(100000, 999999))


def send_verification_code(email: str) -> bool:
    """
    生成验证码，存入Redis，并发送邮件。
    """
    code = generate_email_code()
    cache_key = f"email_code_{email}"

    # 将验证码存入 Redis，有效期 5 分钟 (300 秒)
    cache.set(cache_key, code, timeout=300)

    subject = '【AI模拟面试平台】您的注册验证码'
    message = f'您好！\n\n您的注册验证码是：{code}\n\n该验证码5分钟内有效，请勿泄露给他人。\n\n感谢您使用AI模拟面试平台！'

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        print(f"成功发送验证码 {code} 到 {email}")
        return True
    except Exception as e:
        print(f"发送邮件到 {email} 时失败: {e}")
        return False