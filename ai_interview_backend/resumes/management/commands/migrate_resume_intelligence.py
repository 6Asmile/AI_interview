import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from resumes.json_resume import legacy_resume_to_json_resume
from resumes.models import Resume, ResumeAsset, ResumeVersion
from resumes.schema import JSON_RESUME_SCHEMA_VERSION, sha256_json, validate_resume
from resumes.studio import ensure_studio
from resumes.versioning import create_resume_version, ensure_resume_version


class Command(BaseCommand):
    help = '可重复地归一化旧简历，建立 Resume Intelligence 草稿、设计版本与源文件资产。'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--resume-id', type=int)
        parser.add_argument('--check-only', action='store_true')

    def handle(self, *args, **options):
        queryset = Resume.objects.select_related('user', 'current_version', 'current_design_revision').order_by('pk')
        if options['user_id']:
            queryset = queryset.filter(user_id=options['user_id'])
        if options['resume_id']:
            queryset = queryset.filter(pk=options['resume_id'])
        counts = {'checked': 0, 'versions': 0, 'studios': 0, 'assets': 0, 'errors': 0}
        for resume_id in queryset.values_list('pk', flat=True).iterator():
            counts['checked'] += 1
            try:
                with transaction.atomic():
                    resume = Resume.objects.select_for_update().select_related('user', 'current_version').get(pk=resume_id)
                    current = resume.current_version
                    if options['check_only']:
                        if not current:
                            raise ValueError('missing_current_version')
                        validate_resume(current.resume_json)
                        if current.schema_version != JSON_RESUME_SCHEMA_VERSION or not current.content_hash:
                            raise ValueError('canonical_version_required')
                        if not hasattr(resume, 'draft') or not resume.current_design_revision_id:
                            raise ValueError('studio_snapshot_required')
                        continue
                    if not current:
                        current = ensure_resume_version(resume, resume.user)
                        counts['versions'] += 1
                    elif current.schema_version != JSON_RESUME_SCHEMA_VERSION or not current.content_hash:
                        payload = validate_resume(current.resume_json or legacy_resume_to_json_resume(resume))
                        current = create_resume_version(
                            resume=resume,
                            resume_json=payload,
                            user=resume.user,
                            source=ResumeVersion.Source.LEGACY_MIGRATION,
                            change_summary='归一化到 JSON Resume 1.3.1',
                            parent=current,
                        )
                        counts['versions'] += 1
                    ensure_studio(resume, resume.user)
                    counts['studios'] += 1
                    if resume.file and not resume.assets.filter(kind=ResumeAsset.Kind.SOURCE).exists():
                        digest = hashlib.sha256()
                        with resume.file.open('rb') as source:
                            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                                digest.update(chunk)
                        ResumeAsset.objects.create(
                            resume=resume,
                            kind=ResumeAsset.Kind.SOURCE,
                            file=resume.file.name,
                            original_name=resume.file.name.rsplit('/', 1)[-1],
                            size_bytes=getattr(resume.file, 'size', 0),
                            checksum_sha256=digest.hexdigest(),
                            metadata={'legacy_file_pointer': resume.file.name},
                        )
                        counts['assets'] += 1
            except Exception as exc:
                counts['errors'] += 1
                self.stderr.write(f'resume={resume_id}: {exc}')
        self.stdout.write(self.style.SUCCESS(str(counts)))
        if counts['errors']:
            raise CommandError(f'{counts["errors"]} 份简历未通过迁移/校验。')
