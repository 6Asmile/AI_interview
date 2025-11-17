# ai-interview-backend/chat/views.py (新建文件)
from django.shortcuts import get_object_or_404 # <-- 导入 get_object_or_404
from rest_framework.views import APIView # <-- 导入 APIView
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from users.models import User

# --- 新增视图 ---
class StartConversationView(APIView):
    """
    根据用户ID获取或创建一个对话。
    POST /api/v1/conversations/start_with/<user_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id, *args, **kwargs):
        # 1. 验证目标用户是否存在
        target_user = get_object_or_404(User, id=user_id)

        # 2. 验证不能和自己创建对话
        if request.user == target_user:
            return Response(
                {"error": "You cannot start a conversation with yourself."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. 使用我们之前创建的模型管理器方法来获取或创建对话
        conversation, created = Conversation.objects.get_or_create_conversation(request.user, target_user)

        # 4. 序列化对话数据并返回
        # 传递 context 是为了让 serializer 能访问到 request 对象，从而计算 unread_count
        serializer = ConversationSerializer(conversation, context={'request': request})

        # 根据是新建还是找到，返回不同的状态码
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        return Response(serializer.data, status=response_status)


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    一个只读的 ViewSet，用于获取对话列表。
    - GET /api/v1/conversations/
    """
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """确保用户只能看到自己参与的对话"""
        return self.request.user.conversations.all().order_by('-updated_at')

class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    一个只读的 ViewSet，用于获取特定对话的历史消息。
    - GET /api/v1/conversations/{conversation_pk}/messages/
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        根据 URL 中的 conversation_pk，获取对应对话的消息。
        并确保当前用户是该对话的参与者之一。
        """
        conversation_pk = self.kwargs.get('conversation_pk')
        try:
            # 验证当前用户是否属于该对话
            conversation = self.request.user.conversations.get(pk=conversation_pk)
            return conversation.messages.all().order_by('-timestamp')
        except Conversation.DoesNotExist:
            # 如果不属于，返回一个空 queryset，DRF 会自动处理为 404 Not Found
            return Message.objects.none()