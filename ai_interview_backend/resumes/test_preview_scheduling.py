from django.test import TestCase
from core.models import OperationDispatchOutbox
from core.operations import claim_operation
from resumes.models import Resume, ResumeArtifact
from resumes.operation_service import create_resume_operation
from users.models import User


class PreviewSchedulingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='preview-fixture', email='preview@example.test', password='test')
        self.resume = Resume.objects.create(user=self.user, title='合成测试简历')

    def artifact(self, etag):
        return ResumeArtifact.objects.create(resume=self.resume, format='preview', cache_key=etag, draft_etag=etag)

    def schedule(self, artifact):
        return create_resume_operation(user=self.user, resume=self.resume,
            operation_type='resume.preview', title='合成预览', artifact=artifact)[0]

    def test_same_artifact_reuses_operation(self):
        artifact = self.artifact('same')
        first = self.schedule(artifact)
        self.assertEqual(self.schedule(artifact).pk, first.pk)
        self.assertEqual(OperationDispatchOutbox.objects.count(), 1)

    def test_new_draft_cancels_only_queued_preview(self):
        first = self.schedule(self.artifact('old'))
        running = self.schedule(self.artifact('running'))
        claim_operation(running.pk, worker_id='fixture')
        newest = self.schedule(self.artifact('new'))
        first.refresh_from_db()
        running.refresh_from_db()
        self.assertEqual(first.status, 'canceled')
        self.assertEqual(running.status, 'claimed')
        self.assertEqual(newest.status, 'pending')

    def test_resume_ai_queue_is_not_interview_queue(self):
        from django.conf import settings
        from resumes.versioning import create_resume_version
        from resumes.models import ResumeQualityReport
        version = create_resume_version(resume=self.resume, user=self.user,
            resume_json={'basics': {'name': '合成候选人'}}, change_summary='合成初始版本')
        report = ResumeQualityReport.objects.create(resume=self.resume, content_version=version)
        operation, _ = create_resume_operation(user=self.user, resume=self.resume,
            operation_type='resume.quality_review', title='合成质量复核', quality_report=report)
        self.assertEqual(operation.dispatches.get().queue, settings.CELERY_RESUME_AI_QUEUE)
        self.assertNotEqual(operation.dispatches.get().queue, settings.CELERY_AGENT_QUEUE)
