import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User

from .models import Conversation, ConversationParticipantState, Message, UserBlock


class ReliableChatTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='chat-owner', email='owner@example.com', password='pass12345')
        self.peer = User.objects.create_user(username='chat-peer', email='peer@example.com', password='pass12345')
        self.outsider = User.objects.create_user(username='chat-outsider', email='outsider@example.com', password='pass12345')
        self.conversation, _ = Conversation.objects.get_or_create_conversation(self.owner, self.peer)

    def test_conversation_creation_initializes_one_state_per_participant(self):
        same, created = Conversation.objects.get_or_create_conversation(self.peer, self.owner)

        self.assertFalse(created)
        self.assertEqual(same.id, self.conversation.id)
        self.assertEqual(
            ConversationParticipantState.objects.filter(conversation=self.conversation).count(),
            2,
        )

    def test_client_message_id_is_idempotent_within_sender_and_conversation(self):
        client_message_id = uuid.uuid4()
        Message.objects.create(
            conversation=self.conversation,
            sender=self.owner,
            client_message_id=client_message_id,
            content='first',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.create(
                conversation=self.conversation,
                sender=self.owner,
                client_message_id=client_message_id,
                content='duplicate',
            )

    def test_outsider_cannot_read_messages_and_block_prevents_new_conversation(self):
        Message.objects.create(conversation=self.conversation, sender=self.owner, content='private')
        client = APIClient()
        client.force_authenticate(self.outsider)

        response = client.get(f'/api/v1/conversations/{self.conversation.id}/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('results', response.data), [])

        UserBlock.objects.create(blocker=self.owner, blocked=self.outsider)
        blocked = client.post(f'/api/v1/conversations/start_with/{self.owner.id}/')
        self.assertEqual(blocked.status_code, 403)
