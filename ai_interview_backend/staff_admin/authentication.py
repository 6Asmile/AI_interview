from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.cookie_auth import enforce_csrf
from .models import StaffSession
from .security import session_token_hash


class StaffSessionAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw = request.COOKIES.get(getattr(settings, 'STAFF_SESSION_COOKIE_NAME', 'ifaceoff_staff_session'))
        if not raw:
            return None
        session = StaffSession.objects.select_related('account').filter(
            token_hash=session_token_hash(raw), revoked_at__isnull=True, expires_at__gt=timezone.now(),
            account__status='active',
        ).first()
        if not session:
            raise AuthenticationFailed('员工会话无效或已过期。', code='staff_session_expired')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            enforce_csrf(request)
        return session.account, session
