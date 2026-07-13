from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User

from .models import CareerFact, JobApplication, JobTarget


class CareerWorkspaceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='career-owner', email='career-owner@example.com', password='pass12345'
        )
        self.other = User.objects.create_user(
            username='career-other', email='career-other@example.com', password='pass12345'
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_career_facts_are_private_and_can_be_confirmed(self):
        own = CareerFact.objects.create(
            user=self.user,
            fact_type=CareerFact.FactType.PROJECT,
            title='真实项目',
            description='负责检索服务',
        )
        CareerFact.objects.create(
            user=self.other,
            fact_type=CareerFact.FactType.PROJECT,
            title='其他用户项目',
        )

        response = self.client.get('/api/v2/career-facts/')
        self.assertEqual(response.status_code, 200)
        rows = response.data.get('results', response.data)
        self.assertEqual([row['id'] for row in rows], [own.id])

        confirmed = self.client.post(f'/api/v2/career-facts/{own.id}/confirm/')
        self.assertEqual(confirmed.status_code, 200)
        own.refresh_from_db()
        self.assertEqual(own.verification_status, CareerFact.VerificationStatus.CONFIRMED)

    def test_application_rejects_another_users_job_target(self):
        foreign_target = JobTarget.objects.create(
            user=self.other,
            company_name='Other Corp',
            position_name='Backend Engineer',
        )

        response = self.client.post(
            '/api/v2/applications/',
            {'job_target': foreign_target.id, 'status': JobApplication.Status.APPLIED},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobApplication.objects.filter(user=self.user).exists())

    def test_dashboard_uses_real_owned_records(self):
        JobTarget.objects.create(
            user=self.user,
            company_name='Ifaceoff',
            position_name='AI Engineer',
        )
        response = self.client.get('/api/v2/career-dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['active_job_targets'], 1)
