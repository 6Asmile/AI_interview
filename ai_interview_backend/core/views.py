import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView


class WebSocketTicketSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=['chat', 'interview_speech'])
    resource_id = serializers.CharField(max_length=80)


def websocket_ticket_cache_key(ticket: str) -> str:
    digest = hashlib.sha256(ticket.encode('utf-8')).hexdigest()
    return f'ws_ticket:{digest}'


class WebSocketTicketView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = WebSocketTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data['scope']
        resource_id = serializer.validated_data['resource_id']
        if scope == 'chat':
            from users.models import User
            from chat.models import UserBlock
            try:
                peer_id = int(resource_id)
            except ValueError:
                raise serializers.ValidationError({'resource_id': '聊天用户 ID 无效。'})
            if peer_id == request.user.id or not User.objects.filter(pk=peer_id, status=User.Status.NORMAL).exists():
                raise serializers.ValidationError({'resource_id': '聊天用户不存在或不可用。'})
            if UserBlock.objects.filter(blocker_id__in=[request.user.id, peer_id], blocked_id__in=[request.user.id, peer_id]).exists():
                return Response({'code': 'conversation_blocked', 'message': '当前用户之间无法建立连接。'}, status=status.HTTP_403_FORBIDDEN)
            resource_id = str(peer_id)
        else:
            from interviews.models import InterviewSession
            if not InterviewSession.objects.filter(pk=resource_id, user=request.user).exists():
                return Response({'code': 'session_not_found', 'message': '面试会话不存在。'}, status=status.HTTP_404_NOT_FOUND)
        ttl = max(30, min(60, int(getattr(settings, 'WS_TICKET_TTL_SECONDS', 45))))
        ticket = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(seconds=ttl)
        caches['realtime'].set(websocket_ticket_cache_key(ticket), {
            'user_id': request.user.id,
            'scope': scope,
            'resource_id': resource_id,
            'expires_at': expires_at.isoformat(),
        }, timeout=ttl)
        return Response({
            'ticket': ticket,
            'scope': scope,
            'resource_id': resource_id,
            'expires_at': expires_at.isoformat(),
        }, status=status.HTTP_201_CREATED)
