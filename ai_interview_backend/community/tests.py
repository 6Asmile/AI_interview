import hashlib
import hmac
import json

from django.test import override_settings, TestCase
from rest_framework.test import APIClient

from users.models import User

from .models import CommunityIdentity, CommunityWebhookEvent


@override_settings(DISCOURSE_WEBHOOK_SECRET='webhook-secret')
class CommunityIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='community-user', email='community@example.com', password='pass12345'
        )
        self.client = APIClient()

    def test_webhook_rejects_invalid_signature(self):
        response = self.client.post(
            '/api/v1/community/discourse/webhook/',
            {'user': {'external_id': str(self.user.id)}},
            format='json',
            HTTP_X_DISCOURSE_EVENT_SIGNATURE='invalid',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CommunityWebhookEvent.objects.exists())

    def test_webhook_is_signed_and_idempotent(self):
        payload = json.dumps({
            'user': {
                'external_id': str(self.user.id),
                'id': 42,
                'username': 'community-user',
                'trust_level': 2,
            }
        }, separators=(',', ':')).encode('utf-8')
        signature = hmac.new(b'webhook-secret', payload, hashlib.sha256).hexdigest()
        headers = {
            'HTTP_X_DISCOURSE_EVENT_SIGNATURE': signature,
            'HTTP_X_DISCOURSE_EVENT_ID': 'event-42',
            'HTTP_X_DISCOURSE_EVENT': 'user_updated',
        }

        first = self.client.generic(
            'POST', '/api/v1/community/discourse/webhook/', payload, content_type='application/json', **headers
        )
        second = self.client.generic(
            'POST', '/api/v1/community/discourse/webhook/', payload, content_type='application/json', **headers
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data['duplicate'])
        self.assertEqual(CommunityWebhookEvent.objects.filter(event_id='event-42').count(), 1)
        identity = CommunityIdentity.objects.get(user=self.user)
        self.assertEqual(identity.discourse_user_id, 42)
        self.assertEqual(identity.trust_level, 2)

    @override_settings(MEILISEARCH_URL='')
    def test_public_search_reports_explicit_degradation(self):
        response = self.client.get('/api/v1/community/search/?q=django')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])
        self.assertTrue(response.data['degraded'])
        self.assertEqual(response.data['reason'], 'meilisearch_not_configured')
