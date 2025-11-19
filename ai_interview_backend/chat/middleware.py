# ai_interview_backend/chat/middleware.py (修复版)

from django.db import close_old_connections
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def get_user(user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JwtAuthMiddleware:
    """
    自定义中间件：从 WebSocket 连接的查询参数中提取 JWT Token 并进行验证
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # 关闭旧的数据库连接，防止连接泄漏
        close_old_connections()

        # 解析查询字符串 (例如: ?token=eyJhbGci...)
        query_string = parse_qs(scope["query_string"].decode("utf8"))
        token = query_string.get("token")

        if token:
            try:
                # 1. 验证 Token 有效性
                UntypedToken(token[0])

                # 2. 解码 Token 获取 User ID
                decoded_data = jwt_decode(token[0], settings.SECRET_KEY, algorithms=["HS256"])

                # 3. 获取用户对象
                scope["user"] = await get_user(decoded_data["user_id"])

            except (InvalidToken, TokenError, Exception) as e:
                print(f"JWT WebSocket Auth Failed: {e}")
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)