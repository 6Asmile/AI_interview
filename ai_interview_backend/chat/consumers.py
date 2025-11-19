# ai-interview-backend/chat/consumers.py (最终修复版)

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message, Conversation
from users.models import User


class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        """
        【代码风格优化】在 __init__ 方法中初始化所有实例属性，以消除 linter 警告。
        """
        super().__init__(*args, **kwargs)
        self.user = None
        self.other_user = None
        self.other_user_id = None
        self.room_group_name = None

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            print("WebSocket Auth Failed: User not authenticated")  # 添加日志
            await self.close()
            return

        try:
            self.other_user_id = int(self.scope['url_route']['kwargs']['user_id'])
            if self.user.id == self.other_user_id:
                await self.close()
                return
            self.other_user = await self.get_user(self.other_user_id)
        except (ValueError, User.DoesNotExist):
            await self.close()
            return

        user_ids = sorted([self.user.id, self.other_user_id])
        self.room_group_name = f'chat_{user_ids[0]}_{user_ids[1]}'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # 仅当 room_group_name 被成功初始化后才执行 discard 操作
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        【核心修复】更新 receive 方法的签名以匹配父类。
        处理从 WebSocket 接收到的所有消息。
        """
        if not text_data:
            return  # 如果没有文本数据，则直接返回

        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing_indicator':
                await self.handle_typing_indicator(data)
            elif message_type == 'read_messages':
                await self.handle_read_messages(data)

        except json.JSONDecodeError:
            pass  # 忽略无效的 JSON

    async def handle_chat_message(self, data):
        """处理并广播聊天消息"""
        message_data = {
            'content': data.get('content', ''),
            'message_type': data.get('message_type', 'text'),
            'file_url': data.get('file_url')
        }
        saved_message = await self.save_message(**message_data)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat_message',
                'message': saved_message
            }
        )

    async def handle_typing_indicator(self, data):
        """处理并广播“正在输入”状态"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_typing_indicator',
                'sender_id': self.user.id,
                'is_typing': data.get('is_typing', False)
            }
        )

    async def handle_read_messages(self, data):
        """处理消息已读回执"""
        conversation, _ = await database_sync_to_async(Conversation.objects.get_or_create_conversation)(self.user,
                                                                                                        self.other_user)
        await self.mark_messages_as_read(conversation)

    # --- 广播处理器 ---
    async def broadcast_chat_message(self, event):
        """将格式化后的聊天消息发送给客户端"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))

    async def broadcast_typing_indicator(self, event):
        """将“正在输入”事件发送给客户端，但排除发送者自己"""
        if self.user.id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': 'typing_indicator',
                'is_typing': event['is_typing']
            }))

    # --- 数据库操作 ---
    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)

    @database_sync_to_async
    def save_message(self, content, message_type, file_url=None):
        conversation, _ = Conversation.objects.get_or_create_conversation(self.user, self.other_user)
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type=message_type,
            file_url=file_url
        )
        conversation.save()
        return {
            "id": message.id,
            "sender": {"id": self.user.id, "username": self.user.username,
                       "avatar": self.user.avatar.url if self.user.avatar else None},
            "content": message.content,
            "message_type": message.message_type,
            "file_url": message.file_url,
            "timestamp": message.timestamp.isoformat()
        }

    @database_sync_to_async
    def mark_messages_as_read(self, conversation):
        """将此对话中所有对方发送的未读消息标记为已读"""
        conversation.messages.filter(sender=self.other_user, is_read=False).update(is_read=True)