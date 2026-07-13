import hashlib
import os

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User

from .models import (
    Conversation,
    ConversationParticipantState,
    Message,
    MessageAttachment,
    MessageReport,
    UserBlock,
)
from .serializers import (
    ConversationSerializer,
    MessageAttachmentSerializer,
    MessageReportSerializer,
    MessageSerializer,
    UserBlockSerializer,
)
from .security import scan_attachment


def _blocked(user1, user2):
    return UserBlock.objects.filter(blocker=user1, blocked=user2).exists() or UserBlock.objects.filter(blocker=user2, blocked=user1).exists()


class StartConversationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id, *args, **kwargs):
        target_user = get_object_or_404(User, id=user_id)
        if request.user == target_user:
            return Response({'error': '不能和自己创建对话。'}, status=status.HTTP_400_BAD_REQUEST)
        if _blocked(request.user, target_user):
            return Response({'error': '当前用户之间无法创建对话。'}, status=status.HTTP_403_FORBIDDEN)
        conversation, created = Conversation.objects.get_or_create_conversation(request.user, target_user)
        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.conversations.prefetch_related('participants', 'participant_states', 'messages').order_by('-updated_at')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        last_message = conversation.messages.order_by('-id').first()
        state, _ = ConversationParticipantState.objects.get_or_create(conversation=conversation, user=request.user)
        state.last_read_message = last_message
        state.save(update_fields=['last_read_message', 'updated_at'])
        conversation.messages.exclude(sender=request.user).filter(is_read=False).update(
            is_read=True,
            delivery_status=Message.DeliveryStatus.READ,
        )
        return Response({'last_read_message_id': last_message.id if last_message else None})

    @action(detail=True, methods=['patch'], url_path='preferences')
    def preferences(self, request, pk=None):
        conversation = self.get_object()
        state, _ = ConversationParticipantState.objects.get_or_create(conversation=conversation, user=request.user)
        for field in ('muted', 'archived'):
            if field in request.data:
                setattr(state, field, bool(request.data[field]))
        state.save()
        return Response({'muted': state.muted, 'archived': state.archived})


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_pk = self.kwargs.get('conversation_pk')
        conversation = self.request.user.conversations.filter(pk=conversation_pk).first()
        if not conversation:
            return Message.objects.none()
        return conversation.messages.select_related('sender', 'reply_to', 'reply_to__sender').prefetch_related('attachments').order_by('-timestamp')

    @action(detail=True, methods=['patch'])
    def edit(self, request, conversation_pk=None, pk=None):
        message = self.get_object()
        if message.sender_id != request.user.id or message.revoked_at:
            raise PermissionDenied('只能编辑自己未撤回的消息。')
        if message.message_type != Message.MessageType.TEXT:
            raise ValidationError('只有文本消息可以编辑。')
        content = str(request.data.get('content') or '').strip()
        if not content or len(content) > 5000:
            raise ValidationError({'content': '消息长度应为 1-5000 字。'})
        message.content = content
        message.edited_at = timezone.now()
        message.save(update_fields=['content', 'edited_at'])
        return Response(self.get_serializer(message).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, conversation_pk=None, pk=None):
        message = self.get_object()
        if message.sender_id != request.user.id:
            raise PermissionDenied('只能撤回自己的消息。')
        if not message.revoked_at:
            message.revoked_at = timezone.now()
            message.content = ''
            message.save(update_fields=['revoked_at', 'content'])
        return Response(self.get_serializer(message).data)

    @action(detail=True, methods=['post'])
    def report(self, request, conversation_pk=None, pk=None):
        message = self.get_object()
        if message.sender_id == request.user.id:
            raise ValidationError('不能举报自己的消息。')
        serializer = MessageReportSerializer(data={
            'message': message.id,
            'reason': request.data.get('reason', ''),
            'detail': request.data.get('detail', ''),
        })
        serializer.is_valid(raise_exception=True)
        report, created = MessageReport.objects.get_or_create(
            reporter=request.user,
            message=message,
            defaults=serializer.validated_data,
        )
        return Response(MessageReportSerializer(report).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AttachmentUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser]
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.docx', '.xlsx', '.txt', '.md', '.mp3', '.wav', '.webm', '.mp4'}

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            raise ValidationError({'file': '请选择文件。'})
        extension = os.path.splitext(uploaded.name)[1].lower()
        if extension not in self.allowed_extensions:
            raise ValidationError({'file': '该文件类型不允许发送。'})
        max_bytes = 20 * 1024 * 1024
        if uploaded.size > max_bytes:
            raise ValidationError({'file': '附件不能超过 20MB。'})
        digest = hashlib.sha256()
        content = bytearray()
        for chunk in uploaded.chunks():
            digest.update(chunk)
            content.extend(chunk)
        uploaded.seek(0)
        clean, scan_engine, scan_detail = scan_attachment(bytes(content))
        if not clean:
            raise ValidationError({'file': f'附件安全扫描未通过：{scan_detail}'})
        attachment = MessageAttachment.objects.create(
            uploader=request.user,
            file=uploaded,
            original_name=os.path.basename(uploaded.name)[:255],
            mime_type=(uploaded.content_type or 'application/octet-stream')[:120],
            size=uploaded.size,
            sha256=digest.hexdigest(),
            scan_status=MessageAttachment.ScanStatus.CLEAN,
            scan_engine=scan_engine,
            scan_detail=scan_detail,
        )
        return Response(MessageAttachmentSerializer(attachment, context={'request': request}).data, status=status.HTTP_201_CREATED)


class UserBlockViewSet(viewsets.ModelViewSet):
    serializer_class = UserBlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserBlock.objects.filter(blocker=self.request.user).select_related('blocked')

    def perform_create(self, serializer):
        blocked = serializer.validated_data['blocked']
        if blocked.id == self.request.user.id:
            raise ValidationError('不能屏蔽自己。')
        serializer.save(blocker=self.request.user)
