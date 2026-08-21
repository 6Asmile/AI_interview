from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User

from core.models import OperationDispatchOutbox
from resumes.models import Resume, ResumeVersion

from .models import (
    CareerFact, Company, JobApplication, JobMatchAnalysis, JobPosting, JobPostingRevision,
    JobTarget,
)
from .services import stable_hash


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

    def test_published_company_job_is_frozen_when_saved(self):
        company = Company.objects.create(
            name='可信企业', slug='trusted-company', status=Company.Status.VERIFIED,
            created_by=self.other, verified_at=timezone.now(),
        )
        posting = JobPosting.objects.create(
            company=company, title='AI 工程师', status=JobPosting.Status.PUBLISHED,
            created_by=self.other, published_at=timezone.now(),
        )
        revision = JobPostingRevision.objects.create(
            posting=posting, version=1, title='AI 工程师', jd_text='Python RAG',
            content_hash=stable_hash({'jd_text': 'Python RAG'}), created_by=self.other,
            approved_at=timezone.now(),
        )
        posting.current_revision = revision
        posting.save(update_fields=['current_revision'])

        response = self.client.post(
            f'/api/v2/jobs/{posting.pk}/save-as-target/',
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='save-job-once',
        )

        self.assertEqual(response.status_code, 201)
        target = JobTarget.objects.get(user=self.user, job_posting=posting)
        self.assertEqual(target.job_posting_revision_id, revision.pk)
        self.assertEqual(target.jd_text, 'Python RAG')

    @patch('careers.views.admit_expensive_operation')
    def test_match_analysis_returns_standard_operation_envelope(self, _admit):
        target = JobTarget.objects.create(
            user=self.user, company_name='iFaceoff', position_name='Backend',
            jd_text='Python Django', jd_snapshot_hash=stable_hash({'jd_text': 'Python Django'}),
        )
        resume = Resume.objects.create(user=self.user, title='主简历')
        version = ResumeVersion.objects.create(
            resume=resume, version_number=1,
            resume_json={'basics': {'name': 'Candidate'}, 'skills': [{'name': 'Python'}]},
            created_by=self.user,
        )
        response = self.client.post(
            f'/api/v2/job-targets/{target.pk}/match-analyses/',
            {'resume_version_id': version.pk},
            format='json',
            HTTP_IDEMPOTENCY_KEY='match-once',
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['status'], 'accepted')
        self.assertIn('/api/v2/operations/', response.data['events_url'])
        analysis = JobMatchAnalysis.objects.get(user=self.user, job_target=target)
        self.assertEqual(str(analysis.operation_id), response.data['operation_id'])
        dispatch = OperationDispatchOutbox.objects.get(operation=analysis.operation)
        self.assertEqual(dispatch.payload, {'operation_id': str(analysis.operation_id)})
        self.assertEqual(dispatch.routing_key, 'career.analysis')

    @patch('careers.tasks.execute_job_match_analysis')
    def test_job_match_handler_reloads_analysis_without_legacy_operation_updates(self, execute):
        target = JobTarget.objects.create(
            user=self.user, company_name='iFaceoff', position_name='Backend',
            jd_text='Python Django', jd_snapshot_hash=stable_hash({'jd_text': 'Python Django'}),
        )
        resume = Resume.objects.create(user=self.user, title='Handler resume')
        version = ResumeVersion.objects.create(
            resume=resume,
            version_number=1,
            resume_json={'basics': {'name': 'Candidate'}, 'skills': [{'name': 'Python'}]},
            created_by=self.user,
        )
        analysis = JobMatchAnalysis.objects.create(
            user=self.user,
            job_target=target,
            resume_version=version,
            jd_snapshot=target.jd_text,
            jd_snapshot_hash=target.jd_snapshot_hash,
        )
        from .operation_service import create_job_match_operation

        operation = create_job_match_operation(analysis=analysis, title='Match resume')

        def complete(domain_analysis, *, legacy_operation):
            self.assertIsNone(legacy_operation)
            domain_analysis.status = JobMatchAnalysis.Status.SUCCEEDED
            domain_analysis.score = 88
            domain_analysis.save(update_fields=['status', 'score'])
            return {'status': 'matched'}

        execute.side_effect = complete
        context = Mock()
        context.operation = None
        context.get_operation.return_value = operation
        context.heartbeat.return_value = True

        from .operation_handlers import handle_job_match

        result = handle_job_match(context)

        self.assertEqual(result.result_id, str(analysis.pk))
        self.assertEqual(result.result['status'], JobMatchAnalysis.Status.SUCCEEDED)
        execute.assert_called_once()
        context.raise_if_canceled.assert_called()
        self.assertGreaterEqual(context.heartbeat.call_count, 2)
