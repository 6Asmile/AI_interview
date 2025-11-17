"""
ASGI config for ai_interview_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

# ai_interview_backend/ai_interview_backend/asgi.py (修改)

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # 导入认证中间件
import chat.routing # 导入我们即将创建的 chat 应用的路由

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_interview_backend.settings')

# Django 的原生 HTTP 请求处理
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
  # HTTP 请求依然由 Django 的原生 ASGI 应用处理
  "http": django_asgi_app,

  # WebSocket 请求由我们的路由配置处理
  "websocket": AuthMiddlewareStack( # 使用认证中间件来自动获取 user 对象
        URLRouter(
            chat.routing.websocket_urlpatterns
        )
    ),
})