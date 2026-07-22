from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware, get_token
from rest_framework.exceptions import PermissionDenied


def refresh_cookie_name():
    return getattr(settings, 'AUTH_REFRESH_COOKIE_NAME', 'ifaceoff_refresh')


def set_refresh_cookie(response, value: str):
    response.set_cookie(
        refresh_cookie_name(),
        value,
        max_age=int(getattr(settings, 'AUTH_REFRESH_COOKIE_MAX_AGE', 7 * 24 * 3600)),
        httponly=True,
        secure=bool(getattr(settings, 'AUTH_COOKIE_SECURE', not settings.DEBUG)),
        samesite=getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax'),
        path=getattr(settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/v1/auth/'),
        domain=getattr(settings, 'AUTH_COOKIE_DOMAIN', None) or None,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        refresh_cookie_name(),
        path=getattr(settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/v1/auth/'),
        domain=getattr(settings, 'AUTH_COOKIE_DOMAIN', None) or None,
        samesite=getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax'),
    )


def cookie_refresh_value(request) -> str:
    return str(request.COOKIES.get(refresh_cookie_name()) or '')


def ensure_csrf_token(request) -> str:
    return get_token(request)


def enforce_csrf(request):
    check = CsrfViewMiddleware(lambda req: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f'CSRF 校验失败：{reason}', code='csrf_failed')
