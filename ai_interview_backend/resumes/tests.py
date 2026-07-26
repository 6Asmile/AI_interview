import os
import tempfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from careers.models import CareerFact
from users.models import User

from .services import extract_text_from_file
from .models import Resume, ResumeArtifact, ResumeImportJob
from .quality import build_quality_report
from .rendering import RenderFailure, _rendercv_payload, _safe_text, artifact_cache_key, render_artifact
from .schema import JSON_RESUME_SCHEMA_VERSION, schema_snapshot_hash, strip_internal_metadata, validate_resume
from .sharing import create_share_link, redact_shared_resume, resolve_share
from .studio import ensure_studio
from .templates import default_design, template_catalog
from .versioning import create_resume_version


class ResumeParsingServiceTests(TestCase):
    def _temp_file(self, suffix: str, content: bytes) -> str:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(content)
            return handle.name
        finally:
            handle.close()

    def test_extract_text_prefers_structured_document_parser(self):
        path = self._temp_file('.pdf', b'%PDF fake content')
        try:
            with patch('knowledge.importers.DocumentParsingService.parse', return_value=SimpleNamespace(content='结构化解析的简历内容')) as parse:
                text = extract_text_from_file(path)

            self.assertEqual(text, '结构化解析的简历内容')
            parse.assert_called_once()
        finally:
            os.remove(path)


class ResumeIntelligenceTests(TestCase):
    def _temp_file(self, suffix: str, content: bytes) -> str:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(content)
            return handle.name
        finally:
            handle.close()

    def setUp(self):
        self.user = User.objects.create_user(
            username='resume-owner',
            email='resume-owner@example.com',
            password='pass12345',
        )
        self.other = User.objects.create_user(
            username='resume-other',
            email='resume-other@example.com',
            password='pass12345',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_resume(self, title='主简历'):
        resume = Resume.objects.create(user=self.user, title=title)
        version = create_resume_version(
            resume=resume,
            resume_json={
                'basics': {'name': '候选人', 'email': 'owner@example.com', 'phone': '13800000000'},
                'projects': [{'name': '检索系统', 'description': '将延迟降低 20%'}],
            },
            user=self.user,
            change_summary='初始版本',
        )
        draft, design = ensure_studio(resume, self.user)
        resume.refresh_from_db()
        return resume, version, draft, design

    def test_schema_snapshot_and_internal_ids_are_stable_exports(self):
        payload = validate_resume({'projects': [{'name': 'RAG'}]})
        self.assertEqual(payload['meta']['schemaVersion'], JSON_RESUME_SCHEMA_VERSION)
        self.assertEqual(len(schema_snapshot_hash()), 64)
        self.assertTrue(payload['projects'][0]['x-ifaceoff']['id'])
        exported = strip_internal_metadata(payload)
        self.assertNotIn('x-ifaceoff', exported)
        self.assertNotIn('x-ifaceoff', exported['projects'][0])

    def test_legacy_blank_email_and_url_are_removed_before_strict_validation(self):
        payload = validate_resume({
            'basics': {
                'name': '候选人',
                'email': '',
                'url': '',
                'profiles': [{'network': 'GitHub', 'url': ''}],
            },
        })
        self.assertNotIn('email', payload['basics'])
        self.assertNotIn('url', payload['basics'])

    def test_six_curated_templates_only(self):
        catalog = template_catalog()
        self.assertEqual(len(catalog), 6)
        self.assertTrue(all(item['capabilities']['single_column'] for item in catalog))
        self.assertNotIn('custom_css', {key for item in catalog for key in item})

    def test_six_templates_map_to_distinct_server_owned_rendercv_themes(self):
        themes = {
            _rendercv_payload(
                {'basics': {'name': '候选人'}},
                {**default_design(item['key']), 'show_avatar': True},
                'avatar.png',
            )['design']['theme']
            for item in template_catalog()
        }
        self.assertEqual(len(themes), 6)
        payload = _rendercv_payload(
            {'basics': {'name': '候选人'}},
            {**default_design('ats-classic'), 'show_avatar': True},
            'avatar.png',
        )
        self.assertEqual(payload['cv']['photo'], 'avatar.png')

    def test_version_and_design_revision_are_immutable(self):
        resume, version, _, design = self.create_resume()
        version.change_summary = '篡改'
        with self.assertRaises(ValidationError):
            version.save()
        design.template_key = 'engineering'
        with self.assertRaises(ValidationError):
            design.save()

    def test_draft_etag_conflict_and_commit(self):
        resume, _, draft, _ = self.create_resume()
        response = self.client.patch(
            f'/api/v2/resumes/{resume.id}/draft/',
            {'resume_json': {**draft.resume_json, 'basics': {**draft.resume_json['basics'], 'label': 'AI 工程师'}}},
            format='json',
            HTTP_IF_MATCH=f'"{draft.etag}"',
        )
        self.assertEqual(response.status_code, 200)
        new_etag = response.data['etag']
        conflict = self.client.patch(
            f'/api/v2/resumes/{resume.id}/draft/',
            {'design_json': draft.design_json},
            format='json',
            HTTP_IF_MATCH=f'"{draft.etag}"',
        )
        self.assertEqual(conflict.status_code, 409)
        committed = self.client.post(
            f'/api/v2/resumes/{resume.id}/versions/',
            {'change_summary': '更新目标职位'},
            format='json',
            HTTP_IF_MATCH=f'"{new_etag}"',
        )
        self.assertEqual(committed.status_code, 201)
        self.assertEqual(committed.data['version_number'], 2)

    def test_only_one_default_resume_per_user(self):
        first, *_ = self.create_resume('第一份')
        first.is_default = True
        first.save(update_fields=['is_default'])
        created = self.client.post(
            '/api/v2/resumes/',
            {'title': '第二份', 'status': 'draft', 'is_default': True},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(Resume.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertEqual(Resume.objects.get(pk=created.data['id']).is_default, True)

    def test_evidence_link_requires_confirmed_owned_fact(self):
        resume, _, draft, _ = self.create_resume()
        own = CareerFact.objects.create(
            user=self.user,
            fact_type=CareerFact.FactType.PROJECT,
            title='检索系统',
            verification_status=CareerFact.VerificationStatus.CONFIRMED,
            verified_at=timezone.now(),
        )
        foreign = CareerFact.objects.create(
            user=self.other,
            fact_type=CareerFact.FactType.PROJECT,
            title='他人事实',
            verification_status=CareerFact.VerificationStatus.CONFIRMED,
        )
        response = self.client.post(
            f'/api/v2/resumes/{resume.id}/versions/',
            {
                'change_summary': '绑定证据',
                'evidence_links': [{'json_pointer': '/projects/0', 'fact_id': foreign.id}],
            },
            format='json',
            HTTP_IF_MATCH=f'"{draft.etag}"',
        )
        self.assertEqual(response.status_code, 400)
        accepted = self.client.post(
            f'/api/v2/resumes/{resume.id}/versions/',
            {
                'change_summary': '绑定证据',
                'evidence_links': [{'json_pointer': '/projects/0', 'fact_id': own.id}],
            },
            format='json',
            HTTP_IF_MATCH=f'"{draft.etag}"',
        )
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(len(accepted.data['evidence_links']), 1)

    def test_quality_flags_unverified_metrics(self):
        payload = validate_resume({
            'basics': {'name': '候选人', 'summary': '后端工程师'},
            'projects': [{'name': '服务', 'description': '将接口延迟降低 20%'}],
        })
        report = build_quality_report(payload)
        codes = {item['code'] for item in report['issues']}
        self.assertIn('evidence.metric_unverified', codes)

    def test_share_is_hashed_redacted_password_protected_and_revocable(self):
        resume, version, _, design = self.create_resume()
        link, token = create_share_link(
            resume=resume,
            content_version=version,
            design_revision=design,
            user=self.user,
            password='secret',
        )
        self.assertNotEqual(link.token_hash, token)
        with self.assertRaises(Exception):
            resolve_share(token=token, password='wrong')
        resolved = resolve_share(token=token, password='secret')
        shared = redact_shared_resume(resolved.content_version.resume_json, resolved.field_policy)
        self.assertNotIn('email', shared['basics'])
        self.assertNotIn('phone', shared['basics'])
        link.revoked_at = timezone.now()
        link.save(update_fields=['revoked_at'])
        with self.assertRaises(Exception):
            resolve_share(token=token, password='secret')

    def test_share_download_artifact_uses_redacted_snapshot(self):
        resume, _, _, _ = self.create_resume()
        response = self.client.post(
            f'/api/v2/resumes/{resume.id}/share-links/',
            {
                'allow_download': True,
                'field_policy': {'email': False, 'phone': False, 'address': False, 'image': False},
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        artifact = ResumeArtifact.objects.get(
            resume=resume,
            format=ResumeArtifact.Format.PDF,
            content_version__isnull=True,
        )
        self.assertNotIn('email', artifact.preview_input['basics'])
        self.assertNotIn('phone', artifact.preview_input['basics'])
        self.assertFalse(artifact.preview_design['show_avatar'])

    def test_artifact_cache_is_namespaced_per_resume(self):
        first = artifact_cache_key('content', 'design', 'pdf', namespace='resume:1')
        second = artifact_cache_key('content', 'design', 'pdf', namespace='resume:2')
        self.assertNotEqual(first, second)

    def test_json_and_docx_artifacts_use_same_snapshot(self):
        resume, version, _, design = self.create_resume()
        for output_format in (ResumeArtifact.Format.JSON, ResumeArtifact.Format.DOCX):
            artifact = ResumeArtifact.objects.create(
                resume=resume,
                content_version=version,
                design_revision=design,
                format=output_format,
                cache_key=artifact_cache_key(version.content_hash, design.design_hash, output_format),
            )
            render_artifact(artifact)
            artifact.refresh_from_db()
            self.assertEqual(artifact.status, ResumeArtifact.Status.READY)
            self.assertGreater(artifact.asset.size_bytes, 100)
            self.assertEqual(len(artifact.asset.checksum_sha256), 64)

    def test_renderer_rejects_typst_commands_images_and_html(self):
        for value in (
            '#set page(width: 1pt)',
            '#read("/etc/passwd")',
            '![avatar](file:///etc/passwd)',
            '<script>alert(1)</script>',
        ):
            with self.subTest(value=value), self.assertRaises(RenderFailure):
                _safe_text(value)
        self.assertEqual(_safe_text('使用 **Python** 构建稳定服务'), '使用 **Python** 构建稳定服务')

    def test_resume_create_response_contains_content_and_design_snapshots(self):
        response = self.client.post(
            '/api/v2/resumes/',
            {'title': '完整快照', 'status': 'draft', 'is_default': False},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['current_version']['schema_version'], '1.3.1')
        self.assertEqual(response.data['current_design_revision']['template_key'], 'ats-classic')

    def test_avatar_is_normalized_bound_to_draft_and_removed_from_standard_export(self):
        resume, _, draft, _ = self.create_resume()
        image = BytesIO()
        Image.new('RGB', (24, 24), '#0f766e').save(image, format='JPEG', quality=95)
        uploaded = SimpleUploadedFile('avatar.jpg', image.getvalue(), content_type='image/jpeg')
        response = self.client.post(
            f'/api/v2/resumes/{resume.id}/avatar/',
            {'file': uploaded},
            format='multipart',
            HTTP_IF_MATCH=f'"{draft.etag}"',
        )
        self.assertEqual(response.status_code, 201, response.data)
        draft.refresh_from_db()
        self.assertTrue(draft.resume_json['basics']['image'].startswith('asset:'))
        self.assertNotIn('image', strip_internal_metadata(draft.resume_json)['basics'])
        avatar = resume.assets.get(kind='avatar')
        self.assertEqual(avatar.mime_type, 'image/png')
        self.assertLessEqual(avatar.metadata['width'], 1200)

    def test_import_confirmation_creates_immutable_snapshot_idempotently(self):
        resume = Resume.objects.create(
            user=self.user,
            title='待确认导入',
            status=Resume.Status.PARSED,
        )
        job = ResumeImportJob.objects.create(
            resume=resume,
            user=self.user,
            status=ResumeImportJob.Status.REVIEW_REQUIRED,
            parsed_json=validate_resume({'basics': {'name': '导入候选人'}}),
        )
        first = self.client.post(
            f'/api/v2/resume-imports/{job.id}/confirm/',
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='confirm-import-once',
        )
        second = self.client.post(
            f'/api/v2/resume-imports/{job.id}/confirm/',
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='confirm-import-once',
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(second['X-Idempotent-Replay'], 'true')
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.READY)
        self.assertEqual(resume.versions.count(), 1)

    def test_extract_text_falls_back_to_text_reader_when_parser_fails(self):
        path = self._temp_file('.txt', '候选人有 RAG 和 Agent 项目经验。'.encode('utf-8'))
        try:
            with patch('knowledge.importers.DocumentParsingService.parse', side_effect=RuntimeError('docling unavailable')):
                text = extract_text_from_file(path)

            self.assertIn('RAG 和 Agent 项目经验', text)
        finally:
            os.remove(path)
