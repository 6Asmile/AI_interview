import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from allauth.socialaccount.models import SocialAccount
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuthSession, NotificationPreference, OAuthFlow, PrivacyRequest, User


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


class BrowserCookieAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cookie-user', email='cookie@example.com', password='pass12345')
        self.client = APIClient(enforce_csrf_checks=True)

    def _csrf(self):
        response = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(response.status_code, 200)
        return response.data['csrf_token']

    def test_cookie_login_session_refresh_and_logout(self):
        csrf = self._csrf()
        login = self.client.post(
            '/api/v1/auth/login/',
            {'email': self.user.email, 'password': 'pass12345'},
            format='json', HTTP_X_AUTH_MODE='cookie', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login.status_code, 200)
        self.assertNotIn('refresh', login.data)
        self.assertIn('ifaceoff_refresh', login.cookies)

        csrf = self._csrf()
        session = self.client.post('/api/v1/auth/session/', {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.data['user']['id'], self.user.id)
        self.assertIn('access', session.data)

        csrf = self._csrf()
        logout = self.client.post('/api/v1/auth/logout/', {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(logout.cookies['ifaceoff_refresh']['max-age'], 0)

    def test_browser_login_cors_preflight_allows_custom_auth_headers(self):
        response = self.client.options(
            '/api/v1/auth/login/',
            HTTP_ORIGIN='http://127.0.0.1:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,x-auth-mode,idempotency-key',
        )

        self.assertEqual(response.status_code, 200)
        allowed_headers = response['Access-Control-Allow-Headers'].lower()
        self.assertIn('x-auth-mode', allowed_headers)
        self.assertIn('idempotency-key', allowed_headers)
        exposed_headers = response['Access-Control-Expose-Headers'].lower()
        self.assertIn('x-request-id', exposed_headers)
        self.assertIn('x-agent-run-id', exposed_headers)


@override_settings(
    GITHUB_CLIENT_ID='github-client-id',
    GITHUB_CLIENT_SECRET='github-client-secret',
    GITHUB_OAUTH_CALLBACK_URL='http://127.0.0.1:8000/api/v1/auth/oauth/github/callback/',
    PUBLIC_BACKEND_URL='http://127.0.0.1:8000',
    PUBLIC_FRONTEND_URL='http://127.0.0.1:5173',
)
class GitHubOAuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def _start(self):
        response = self.client.get('/api/v1/auth/oauth/github/start/', {'return_to': '/dashboard/resumes'})
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlparse(response.data['authorize_url']).query)
        return query['state'][0], query

    def _provider_mocks(self, email='octocat@example.com'):
        token = Mock()
        token.raise_for_status.return_value = None
        token.json.return_value = {'access_token': 'provider-access-token'}
        profile = Mock()
        profile.raise_for_status.return_value = None
        profile.json.return_value = {
            'id': 123456, 'login': 'octocat', 'name': 'Octo Cat',
            'avatar_url': 'https://avatars.githubusercontent.com/u/123456',
            'html_url': 'https://github.com/octocat',
        }
        emails = Mock()
        emails.raise_for_status.return_value = None
        emails.json.return_value = [] if email is None else [
            {'email': email, 'verified': True, 'primary': True},
        ]
        return token, profile, emails

    def _callback(self, state, *, email='octocat@example.com', code='oauth-code'):
        token, profile, emails = self._provider_mocks(email)
        with patch('users.views_oauth.requests.post', return_value=token) as exchange, patch(
            'users.views_oauth.requests.get', side_effect=[profile, emails]
        ):
            response = self.client.get(
                '/api/v1/auth/oauth/github/callback/', {'state': state, 'code': code}
            )
        return response, exchange

    def _csrf(self):
        response = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(response.status_code, 200)
        return response.data['csrf_token']

    def test_start_uses_server_state_pkce_and_canonical_callback(self):
        state, query = self._start()
        flow = OAuthFlow.objects.get()

        self.assertEqual(flow.state_hash, hashlib.sha256(state.encode()).hexdigest())
        self.assertNotEqual(flow.state_hash, state)
        self.assertEqual(query['redirect_uri'][0], flow.redirect_uri)
        self.assertEqual(query['code_challenge_method'][0], 'S256')
        self.assertTrue(query['code_challenge'][0])
        self.assertEqual(flow.return_to, '/dashboard/resumes')

    def test_verified_github_email_registers_candidate_and_rejects_code_replay(self):
        state, _ = self._start()
        response, exchange = self._callback(state)

        self.assertEqual(response.status_code, 302)
        self.assertIn('status=success', response.url)
        self.assertIn('ifaceoff_refresh', response.cookies)
        candidate = User.objects.get(email='octocat@example.com')
        self.assertTrue(SocialAccount.objects.filter(user=candidate, provider='github', uid='123456').exists())
        payload = exchange.call_args.kwargs['data']
        self.assertEqual(payload['redirect_uri'], OAuthFlow.objects.get().redirect_uri)
        self.assertTrue(payload['code_verifier'])

        replay, _ = self._callback(state, code='replayed-code')
        self.assertEqual(replay.status_code, 302)
        self.assertIn('oauth_state_invalid', replay.url)
        self.assertEqual(User.objects.filter(email='octocat@example.com').count(), 1)

    def test_existing_email_requires_password_before_linking(self):
        candidate = User.objects.create_user(
            username='existing-candidate', email='octocat@example.com', password='candidate-pass-123'
        )
        state, _ = self._start()
        callback, _ = self._callback(state)
        query = parse_qs(urlparse(callback.url).query)

        self.assertEqual(query['status'][0], 'link_required')
        self.assertFalse(SocialAccount.objects.filter(user=candidate, provider='github').exists())
        csrf = self._csrf()
        denied = self.client.post(
            '/api/v1/auth/oauth/github/link/confirm/',
            {'link_token': query['link_token'][0], 'password': 'wrong-password'},
            format='json', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(denied.status_code, 401)

        csrf = self._csrf()
        confirmed = self.client.post(
            '/api/v1/auth/oauth/github/link/confirm/',
            {'link_token': query['link_token'][0], 'password': 'candidate-pass-123'},
            format='json', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertIn('ifaceoff_refresh', confirmed.cookies)
        self.assertTrue(SocialAccount.objects.filter(user=candidate, provider='github', uid='123456').exists())

    def test_missing_verified_email_does_not_create_candidate(self):
        state, _ = self._start()
        response, _ = self._callback(state, email=None)

        self.assertEqual(response.status_code, 302)
        self.assertIn('github_verified_email_required', response.url)
        self.assertFalse(User.objects.filter(username='octocat').exists())

    def test_public_site_sync_uses_canonical_backend_host(self):
        call_command('sync_public_site', verbosity=0)
        self.assertEqual(Site.objects.get_current().domain, '127.0.0.1:8000')

    def test_public_site_sync_merges_domain_preserved_under_another_pk(self):
        Site.objects.all().delete()
        Site.objects.create(pk=2, domain='127.0.0.1:8000', name='Imported site')

        call_command('sync_public_site', verbosity=0)
        call_command('sync_public_site', verbosity=0)

        self.assertEqual(
            list(Site.objects.values_list('id', 'domain')),
            [(1, '127.0.0.1:8000')],
        )
