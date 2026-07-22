import hashlib
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User
from .models import (
    AdminIdempotencyRecord, StaffAccount, StaffEmailOutbox, StaffInvitation,
    StaffRole, StaffSession,
)


class StaffIdentityIsolationTests(TestCase):
    def setUp(self):
        self.role = StaffRole.objects.create(slug='test-super', name='Test Super', permissions=['*'])
        self.staff = StaffAccount.objects.create_account(
            email='staff@example.com', password='staff-pass-123', display_name='Staff', status=StaffAccount.Status.ACTIVE,
        )
        self.staff.roles.add(self.role)
        self.candidate = User.objects.create_user(username='candidate', email='candidate@example.com', password='pass12345')

    def test_candidate_identity_cannot_access_staff_api(self):
        client = APIClient()
        client.force_authenticate(self.candidate)
        response = client.get('/api/admin/v1/dashboard/summary/')
        self.assertEqual(response.status_code, 403)

    def test_staff_cookie_session_accesses_staff_api(self):
        raw = secrets.token_urlsafe(48)
        StaffSession.objects.create(
            account=self.staff, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            mfa_verified_at=timezone.now(), expires_at=timezone.now() + timedelta(hours=1),
        )
        client = APIClient(enforce_csrf_checks=True)
        client.cookies['ifaceoff_staff_session'] = raw
        response = client.get('/api/admin/v1/dashboard/summary/')
        self.assertEqual(response.status_code, 200)

    def test_staff_idempotency_does_not_use_candidate_user_fk(self):
        client = APIClient()
        client.force_authenticate(self.staff)
        payload = {
            'email': 'invitee@example.com', 'display_name': 'Invitee',
            'roles': [self.role.slug], 'operation_reason': '测试独立员工邀请幂等。',
        }
        first = client.post('/api/admin/v1/staff/', payload, format='json', HTTP_IDEMPOTENCY_KEY='staff-test-key')
        second = client.post('/api/admin/v1/staff/', payload, format='json', HTTP_IDEMPOTENCY_KEY='staff-test-key')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second['X-Idempotent-Replay'], 'true')
        self.assertEqual(AdminIdempotencyRecord.objects.count(), 1)


class StaffInvitationLifecycleTests(TestCase):
    def setUp(self):
        self.role = StaffRole.objects.create(
            slug='super_admin', name='超级管理员', permissions=['*']
        )
        self.inviter = StaffAccount.objects.create_account(
            email='admin@example.com', password='admin-pass-123', display_name='Admin',
            status=StaffAccount.Status.ACTIVE, recovery_codes_confirmed_at=timezone.now(),
        )
        self.inviter.roles.add(self.role)
        self.client = APIClient()
        self.client.force_authenticate(self.inviter)

    def _create_invitation(self):
        response = self.client.post(
            '/api/admin/v1/staff/',
            {
                'email': 'operator@example.com', 'display_name': 'Operator',
                'roles': [self.role.slug], 'operation_reason': '新增平台运营管理员账号。',
            },
            format='json', HTTP_IDEMPOTENCY_KEY='invite-operator-once',
        )
        self.assertEqual(response.status_code, 201)
        token = response.data['activation_url'].split('invite=', 1)[1]
        return response, token

    def test_invitation_requires_mfa_and_recovery_confirmation_before_activation(self):
        response, token = self._create_invitation()
        self.assertEqual(response.data['delivery_status'], 'pending')
        self.assertEqual(StaffEmailOutbox.objects.count(), 1)

        public_client = APIClient(enforce_csrf_checks=True)
        preview = public_client.get(f'/api/admin/v1/auth/invitations/{token}/')
        self.assertEqual(preview.status_code, 200)
        csrf = public_client.get('/api/admin/v1/auth/csrf/').data['csrf_token']
        registered = public_client.post(
            '/api/admin/v1/auth/register/',
            {'invite': token, 'display_name': 'Operator', 'password': 'Secure-Operator-2026!'},
            format='json', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(registered.status_code, 200)
        account = StaffAccount.objects.get(email='operator@example.com')
        self.assertEqual(account.status, StaffAccount.Status.INVITED)
        self.assertEqual(account.invitation.status, StaffInvitation.Status.ACCEPTED)

        csrf = public_client.get('/api/admin/v1/auth/csrf/').data['csrf_token']
        secret_response = public_client.post(
            '/api/admin/v1/auth/security-setup/',
            {'challenge_token': registered.data['challenge_token']},
            format='json', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertTrue(secret_response.data['secret'])
        with patch('staff_admin.views.verify_totp', return_value=True):
            csrf = public_client.get('/api/admin/v1/auth/csrf/').data['csrf_token']
            configured = public_client.post(
                '/api/admin/v1/auth/security-setup/',
                {'challenge_token': registered.data['challenge_token'], 'code': '123456'},
                format='json', HTTP_X_CSRFTOKEN=csrf,
            )
        self.assertEqual(configured.status_code, 200)
        self.assertEqual(len(configured.data['recovery_codes']), 10)
        self.assertNotIn('ifaceoff_staff_session', configured.cookies)
        account.refresh_from_db()
        self.assertEqual(account.status, StaffAccount.Status.INVITED)
        self.assertIsNone(account.recovery_codes_confirmed_at)

        csrf = public_client.get('/api/admin/v1/auth/csrf/').data['csrf_token']
        activated = public_client.post(
            '/api/admin/v1/auth/security-setup/',
            {
                'recovery_confirmation_token': configured.data['recovery_confirmation_token'],
                'recovery_codes_confirmed': True,
            },
            format='json', HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(activated.status_code, 200)
        self.assertIn('ifaceoff_staff_session', activated.cookies)
        account.refresh_from_db()
        self.assertEqual(account.status, StaffAccount.Status.ACTIVE)
        self.assertIsNotNone(account.recovery_codes_confirmed_at)

    def test_cannot_suspend_last_active_super_admin(self):
        response = self.client.patch(
            f'/api/admin/v1/staff/{self.inviter.id}/',
            {'status': StaffAccount.Status.SUSPENDED, 'operation_reason': '验证最后管理员保护机制。'},
            format='json', HTTP_IDEMPOTENCY_KEY='protect-last-super-admin',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'last_super_admin_protected')
        self.inviter.refresh_from_db()
        self.assertEqual(self.inviter.status, StaffAccount.Status.ACTIVE)


class StaffOperationsReadSmokeTests(TestCase):
    def setUp(self):
        role = StaffRole.objects.create(slug='ops-super', name='Ops Super', permissions=['*'])
        self.staff = StaffAccount.objects.create_account(
            email='ops@example.com', password='ops-pass-123', display_name='Ops',
            status=StaffAccount.Status.ACTIVE, recovery_codes_confirmed_at=timezone.now(),
        )
        self.staff.roles.add(role)
        self.candidate = User.objects.create_user(
            username='ops-candidate', email='ops-candidate@example.com', password='pass12345'
        )
        from system.models import ModelAlias, ModelDeployment, RoutePolicy, RoutePolicyTarget
        alias = ModelAlias.objects.create(slug='ops.chat', name='Ops Chat', model_type='chat')
        deployment = ModelDeployment.objects.create(
            name='Ops Deployment', provider='openai_compatible', remote_model='ops-model',
            model_type='chat', base_url='https://gateway.invalid/v1',
        )
        policy = RoutePolicy.objects.create(alias=alias)
        RoutePolicyTarget.objects.create(policy=policy, deployment=deployment)
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_operational_workspaces_render_from_real_database_queries(self):
        paths = [
            '/api/admin/v1/dashboard/summary/',
            '/api/admin/v1/candidates/?search=ops-candidate',
            '/api/admin/v1/interviews/',
            '/api/admin/v1/interview-config/rubrics/',
            '/api/admin/v1/interview-config/templates/',
            '/api/admin/v1/interview-config/datasets/',
            '/api/admin/v1/interview-config/runs/',
            '/api/admin/v1/knowledge-reviews/',
            '/api/admin/v1/agent-runs/',
            '/api/admin/v1/model-gateway/summary/',
            '/api/admin/v1/model-gateway/credentials/',
            '/api/admin/v1/model-gateway/deployments/',
            '/api/admin/v1/model-gateway/aliases/',
            '/api/admin/v1/model-gateway/routes/',
            '/api/admin/v1/model-gateway/budgets/',
            '/api/admin/v1/model-gateway/ledger/',
            '/api/admin/v1/tasks/?status=failed',
            '/api/admin/v1/moderation/reports/',
            '/api/admin/v1/content/operations/',
            '/api/admin/v1/notifications/operations/',
            '/api/admin/v1/analytics/',
            '/api/admin/v1/feature-flags/',
            '/api/admin/v1/maintenance-notices/',
            '/api/admin/v1/audit-logs/',
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.data)

    def test_limited_staff_cannot_open_model_gateway(self):
        role = StaffRole.objects.create(slug='readonly-candidate', name='Candidate Support', permissions=['candidate.support'])
        limited = StaffAccount.objects.create_account(
            email='limited@example.com', password='limited-pass-123', display_name='Limited',
            status=StaffAccount.Status.ACTIVE, recovery_codes_confirmed_at=timezone.now(),
        )
        limited.roles.add(role)
        client = APIClient()
        client.force_authenticate(limited)

        self.assertEqual(client.get('/api/admin/v1/candidates/').status_code, 200)
        self.assertEqual(client.get('/api/admin/v1/model-gateway/summary/').status_code, 403)
