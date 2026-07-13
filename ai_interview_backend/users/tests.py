from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuthSession, NotificationPreference, PrivacyRequest, User


class PersonalSecurityApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='security-user', email='security@example.com', password='pass12345')
        self.other = User.objects.create_user(username='security-other', email='security-other@example.com', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_notification_preferences_are_user_scoped(self):
        NotificationPreference.objects.create(user=self.other, email_enabled=True)

        response = self.client.patch(
            '/api/v1/auth/notification-preferences/',
            {'email_enabled': False, 'digest_frequency': 'none'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(NotificationPreference.objects.get(user=self.user).email_enabled)
        self.assertTrue(NotificationPreference.objects.get(user=self.other).email_enabled)

    def test_user_cannot_revoke_another_users_session(self):
        foreign = AuthSession.objects.create(
            user=self.other,
            refresh_jti='foreign-session-jti',
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(f'/api/v1/auth/sessions/{foreign.id}/revoke/')

        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.revoked_at)

    def test_export_request_contains_owned_data_and_no_password(self):
        response = self.client.post(
            '/api/v1/auth/privacy-requests/',
            {'request_type': PrivacyRequest.RequestType.EXPORT},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        export = PrivacyRequest.objects.get(user=self.user)
        self.assertEqual(export.status, PrivacyRequest.Status.COMPLETED)
        self.assertEqual(export.result['profile']['email'], self.user.email)
        self.assertNotIn('password', export.result['profile'])
