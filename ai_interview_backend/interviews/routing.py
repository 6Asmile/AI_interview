from django.urls import re_path

from . import consumers


websocket_urlpatterns = [
    re_path(r'ws/interviews/(?P<session_id>[0-9a-f-]+)/speech/$', consumers.InterviewSpeechConsumer.as_asgi()),
]
