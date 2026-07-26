import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import override_settings, TestCase
from rest_framework.test import APIClient

from users.models import User

from .models import CommunityContent, CommunityIdentity, CommunityWebhookEvent


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

    @patch('community.views_v2.admit_expensive_operation')
    def test_native_content_redacts_pii_and_requires_review_for_new_user(self, _admit):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/v2/community/contents/',
            {
                'content_type': 'experience',
                'title': '面试经历',
                'body': '可以联系 13800138000 或 candidate@example.com',
                'is_anonymous': True,
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        content = CommunityContent.objects.get(pk=created.data['id'])
        self.assertNotIn('13800138000', content.current_revision.redacted_body)
        self.assertNotIn('candidate@example.com', content.current_revision.redacted_body)

        submitted = self.client.post(
            f'/api/v2/community/contents/{content.pk}/publish/',
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='publish-native-content',
        )
        self.assertEqual(submitted.status_code, 202)
        content.refresh_from_db()
        self.assertEqual(content.status, CommunityContent.Status.PENDING)

    def test_anonymous_content_does_not_expose_author_to_other_users(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/v2/community/contents/',
            {'content_type': 'discussion', 'title': '匿名讨论', 'body': '公开但匿名', 'is_anonymous': True},
            format='json',
        )
        content = CommunityContent.objects.get(pk=created.data['id'])
        content.status = CommunityContent.Status.PUBLISHED
        content.save(update_fields=['status'])
        viewer = User.objects.create_user(username='viewer', email='viewer@example.com', password='pass12345')
        self.client.force_authenticate(viewer)
        response = self.client.get(f'/api/v2/community/contents/{content.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['author'], {'anonymous': True})
