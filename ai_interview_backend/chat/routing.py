# ai-interview-backend/chat/routing.py (新建文件)

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # URL 格式: ws://<host>/ws/chat/<other_user_id>/
    re_path(r'ws/chat/(?P<user_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
]