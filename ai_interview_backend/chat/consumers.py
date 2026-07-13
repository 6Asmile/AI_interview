import json
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import transaction
from django.utils import timezone

from users.models import User

from .models import (
    ChatOutbox,
    Conversation,
    ConversationParticipantState,
    Message,
    MessageAttachment,
    UserBlock,
)


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.other_user = None
        self.other_user_id = None
        self.room_group_name = None

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return
        try:
            self.other_user_id = int(self.scope['url_route']['kwargs']['user_id'])
            if self.user.id == self.other_user_id:
                raise ValueError
            self.other_user = await self.get_user(self.other_user_id)
            if await self.is_blocked():
                await self.close(code=4403)
                return
        except (ValueError, User.DoesNotExist):
            await self.close(code=4404)
            return
        user_ids = sorted([self.user.id, self.other_user_id])
        self.room_group_name = f'chat_{user_ids[0]}_{user_ids[1]}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'connection.ready'})

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error('invalid_json', '消息格式不是有效 JSON。')
            return
        message_type = data.get('type')
        try:
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing_indicator':
                await self.handle_typing_indicator(data)
            elif message_type == 'read_messages':
                await self.handle_read_messages()
            else:
                await self.send_error('unsupported_event', '不支持的事件类型。')
        except ValueError as exc:
            await self.send_error(str(exc), '消息未发送。', data.get('client_message_id'))

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False, default=str))

    async def send_error(self, code, message, client_message_id=None):
        await self.send_json({'type': 'error', 'code': code, 'message': message, 'client_message_id': client_message_id})

    async def handle_chat_message(self, data):
        content = str(data.get('content') or '').strip()
        message_type = str(data.get('message_type') or Message.MessageType.TEXT)
        if message_type not in Message.MessageType.values:
            raise ValueError('invalid_message_type')
        if len(content) > 5000:
            raise ValueError('message_too_long')
        if message_type == Message.MessageType.TEXT and not content:
            raise ValueError('empty_message')
        saved_message = await self.save_message(
            content=content,
            message_type=message_type,
            client_message_id=data.get('client_message_id'),
            reply_to_id=data.get('reply_to_id'),
            attachment_id=data.get('attachment_id'),
        )
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'broadcast_chat_message', 'message': saved_message},
        )
        await self.mark_outbox_published(saved_message['outbox_event_id'])

    async def handle_typing_indicator(self, data):
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'broadcast_typing_indicator', 'sender_id': self.user.id, 'is_typing': bool(data.get('is_typing'))},
        )

    async def handle_read_messages(self):
        last_message_id = await self.mark_messages_as_read()
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'broadcast_read_receipt', 'reader_id': self.user.id, 'last_read_message_id': last_message_id},
        )

    async def broadcast_chat_message(self, event):
        message = event['message']
        if self.user.id != message['sender']['id']:
            await self.mark_delivered(message['id'])
            message['delivery_status'] = Message.DeliveryStatus.DELIVERED
        await self.send_json({'type': 'chat_message', 'message': message})

    async def broadcast_typing_indicator(self, event):
        if self.user.id != event['sender_id']:
            await self.send_json({'type': 'typing_indicator', 'is_typing': event['is_typing']})

    async def broadcast_read_receipt(self, event):
        if self.user.id != event['reader_id']:
            await self.send_json({
                'type': 'read_receipt',
                'reader_id': event['reader_id'],
                'last_read_message_id': event['last_read_message_id'],
            })

    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)

    @database_sync_to_async
    def is_blocked(self):
        return UserBlock.objects.filter(blocker=self.user, blocked=self.other_user).exists() or UserBlock.objects.filter(blocker=self.other_user, blocked=self.user).exists()

    @database_sync_to_async
    @transaction.atomic
    def save_message(self, *, content, message_type, client_message_id=None, reply_to_id=None, attachment_id=None):
        if UserBlock.objects.filter(blocker=self.user, blocked=self.other_user).exists() or UserBlock.objects.filter(blocker=self.other_user, blocked=self.user).exists():
            raise ValueError('conversation_blocked')
        conversation, _ = Conversation.objects.get_or_create_conversation(self.user, self.other_user)
        try:
            client_uuid = uuid.UUID(str(client_message_id)) if client_message_id else uuid.uuid4()
        except ValueError:
            raise ValueError('invalid_client_message_id')
        existing = Message.objects.filter(conversation=conversation, sender=self.user, client_message_id=client_uuid).first()
        if existing:
            outbox = existing.outbox_events.order_by('-created_at').first()
            return self._message_payload(existing, outbox)
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(id=reply_to_id, conversation=conversation).first()
            if not reply_to:
                raise ValueError('invalid_reply_target')
        attachment = None
        if attachment_id:
            attachment = MessageAttachment.objects.select_for_update().filter(
                id=attachment_id,
                uploader=self.user,
                message__isnull=True,
                scan_status=MessageAttachment.ScanStatus.CLEAN,
            ).first()
            if not attachment:
                raise ValueError('invalid_attachment')
        if message_type != Message.MessageType.TEXT and not attachment:
            raise ValueError('attachment_required')
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            client_message_id=client_uuid,
            reply_to=reply_to,
            content=content,
            message_type=message_type,
            file_url=attachment.file.url if attachment else None,
            delivery_status=Message.DeliveryStatus.SENT,
        )
        if attachment:
            attachment.message = message
            attachment.save(update_fields=['message'])
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        payload = self._message_payload(message, None)
        outbox = ChatOutbox.objects.create(
            message=message,
            topic=self.room_group_name,
            payload={key: value for key, value in payload.items() if key != 'outbox_event_id'},
        )
        payload['outbox_event_id'] = str(outbox.event_id)
        return payload

    def _message_payload(self, message, outbox):
        return {
            'id': message.id,
            'client_message_id': str(message.client_message_id),
            'sender': {
                'id': self.user.id,
                'username': self.user.username,
                'avatar': self.user.avatar.url if self.user.avatar else None,
            },
            'content': message.content,
            'message_type': message.message_type,
            'file_url': message.file_url,
            'delivery_status': message.delivery_status,
            'reply_to': message.reply_to_id,
            'timestamp': message.timestamp.isoformat(),
            'edited_at': message.edited_at,
            'revoked_at': message.revoked_at,
            'outbox_event_id': str(outbox.event_id) if outbox else '',
        }

    @database_sync_to_async
    def mark_messages_as_read(self):
        conversation, _ = Conversation.objects.get_or_create_conversation(self.user, self.other_user)
        last_message = conversation.messages.order_by('-id').first()
        state, _ = ConversationParticipantState.objects.get_or_create(conversation=conversation, user=self.user)
        state.last_read_message = last_message
        state.save(update_fields=['last_read_message', 'updated_at'])
        conversation.messages.filter(sender=self.other_user, is_read=False).update(is_read=True, delivery_status=Message.DeliveryStatus.READ)
        return last_message.id if last_message else None

    @database_sync_to_async
    def mark_delivered(self, message_id):
        Message.objects.filter(id=message_id, delivery_status=Message.DeliveryStatus.SENT).update(delivery_status=Message.DeliveryStatus.DELIVERED)

    @database_sync_to_async
    def mark_outbox_published(self, event_id):
        ChatOutbox.objects.filter(event_id=event_id).update(status=ChatOutbox.Status.PUBLISHED, published_at=timezone.now())
