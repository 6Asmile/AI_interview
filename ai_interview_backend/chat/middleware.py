import re
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections

from core.views import consume_websocket_ticket


@database_sync_to_async
def get_user(user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(pk=user_id, status=User.Status.NORMAL).first() or AnonymousUser()


@database_sync_to_async
def consume_ticket(ticket, expected_scope, expected_resource):
    return consume_websocket_ticket(
        ticket,
        expected_scope=expected_scope,
        expected_resource=expected_resource,
    )


def _expected_scope(path: str):
    chat = re.fullmatch(r'/ws/chat/(?P<resource>\d+)/?', path)
    if chat:
        return 'chat', chat.group('resource')
    speech = re.fullmatch(r'/ws/interviews/(?P<resource>[0-9a-f-]+)/speech/?', path)
    if speech:
        return 'interview_speech', speech.group('resource')
    return '', ''


class JwtAuthMiddleware:
    """Authenticates WebSockets with a scoped, single-use ticket.

    The legacy JWT query parameter remains available only behind an explicit
    compatibility setting and is disabled by default.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        close_old_connections()
        scope['user'] = AnonymousUser()
        query = parse_qs(scope.get('query_string', b'').decode('utf-8', errors='ignore'))
        ticket = str((query.get('ticket') or [''])[0])
        expected_scope, expected_resource = _expected_scope(scope.get('path', ''))
        if ticket and expected_scope:
            payload = await consume_ticket(ticket, expected_scope, expected_resource)
            if payload:
                scope['user'] = await get_user(payload.get('user_id'))
        elif getattr(settings, 'WS_ALLOW_LEGACY_QUERY_JWT', False):
            token = str((query.get('token') or [''])[0])
            if token:
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    decoded = AccessToken(token)
                    scope['user'] = await get_user(decoded.get('user_id'))
                except Exception:
                    scope['user'] = AnonymousUser()
        return await self.inner(scope, receive, send)
