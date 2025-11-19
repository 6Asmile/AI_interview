from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 注意：这里开头没有 '/'，且使用 re_path
    re_path(r'ws/chat/(?P<user_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
]