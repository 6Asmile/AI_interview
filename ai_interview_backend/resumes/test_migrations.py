from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ResumeIntelligenceMigrationTests(TransactionTestCase):
    """Exercise the historical state used by the Resume intelligence backfill."""

    migrate_from = ('resumes', '0007_backfill_resume_versions')
    migrate_to = (
        'resumes',
        '0008_resumedraft_resumeevidencelink_resumequalityreport_and_more',
    )
    users_target = (
        'users',
        '0005_alter_user_options_user_users_user_email_ci_unique_and_more',
    )

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        targets = [target, self.users_target]
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_empty_database_can_apply_resume_intelligence_migration(self):
        self._migrate(self.migrate_from)
        apps = self._migrate(self.migrate_to)

        ResumeDraft = apps.get_model('resumes', 'ResumeDraft')
        self.assertEqual(ResumeDraft.objects.count(), 0)
        self.assertIn('resume', {field.name for field in ResumeDraft._meta.fields})
        self.assertIn('base_version', {field.name for field in ResumeDraft._meta.fields})

    def test_existing_resume_is_backfilled_once(self):
        old_apps = self._migrate(self.migrate_from)
        User = old_apps.get_model('users', 'User')
        Resume = old_apps.get_model('resumes', 'Resume')
        ResumeVersion = old_apps.get_model('resumes', 'ResumeVersion')

        user = User.objects.create(
            username='docs-migration-candidate',
            email='docs-migration-candidate@example.invalid',
            password='not-a-real-password',
        )
        resume = Resume.objects.create(
            user_id=user.pk,
            title='迁移验证简历',
            file='resumes/docs-migration.txt',
            full_name='合成候选人',
            email='docs-migration-candidate@example.invalid',
            template_name='modern',
            is_default=True,
        )
        version = ResumeVersion.objects.create(
            resume_id=resume.pk,
            version_number=1,
            schema_version='1.0.0',
            resume_json={
                'basics': {'name': '合成候选人'},
                'work': [{'name': '示例公司', 'position': '后端工程师'}],
            },
            layout_json={},
            evidence_snapshot=[],
            source='legacy_migration',
            created_by_id=user.pk,
        )
        Resume.objects.filter(pk=resume.pk).update(current_version_id=version.pk)

        apps = self._migrate(self.migrate_to)
        Resume = apps.get_model('resumes', 'Resume')
        ResumeVersion = apps.get_model('resumes', 'ResumeVersion')
        ResumeDraft = apps.get_model('resumes', 'ResumeDraft')
        ResumeDesignRevision = apps.get_model('resumes', 'ResumeDesignRevision')
        ResumeAsset = apps.get_model('resumes', 'ResumeAsset')

        migrated_resume = Resume.objects.get(pk=resume.pk)
        migrated_version = ResumeVersion.objects.get(pk=version.pk)
        draft = ResumeDraft.objects.get(resume_id=resume.pk)
        design = ResumeDesignRevision.objects.get(resume_id=resume.pk)
        asset = ResumeAsset.objects.get(resume_id=resume.pk, kind='source')

        self.assertEqual(migrated_resume.canonical_schema_version, '1.3.1')
        self.assertEqual(migrated_resume.current_design_revision_id, design.pk)
        self.assertEqual(migrated_version.schema_version, '1.3.1')
        self.assertEqual(migrated_version.language, 'zh-CN')
        self.assertEqual(len(migrated_version.content_hash), 64)
        self.assertEqual(draft.base_version_id, version.pk)
        self.assertEqual(draft.updated_by_id, user.pk)
        self.assertEqual(design.template_key, 'modern-professional')
        self.assertEqual(asset.original_name, 'docs-migration.txt')
        self.assertTrue(asset.metadata.get('checksum_pending'))

        counts_before = {
            'draft': ResumeDraft.objects.count(),
            'design': ResumeDesignRevision.objects.count(),
            'asset': ResumeAsset.objects.count(),
        }
        apps = self._migrate(self.migrate_to)
        self.assertEqual(apps.get_model('resumes', 'ResumeDraft').objects.count(), counts_before['draft'])
        self.assertEqual(
            apps.get_model('resumes', 'ResumeDesignRevision').objects.count(),
            counts_before['design'],
        )
        self.assertEqual(apps.get_model('resumes', 'ResumeAsset').objects.count(), counts_before['asset'])
