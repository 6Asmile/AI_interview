from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import APIException, ValidationError

from .models import Resume, ResumeDesignRevision, ResumeDraft
from .schema import sha256_json, validate_resume
from .templates import default_design, design_hash, validate_design
from .versioning import create_resume_version


class VersionConflict(APIException):
    status_code = 409
    default_code = 'version_conflict'
    default_detail = '草稿已被其他修改更新，请刷新后重试。'


def etag_for(resume_json: dict, design_json: dict, revision: int) -> str:
    return sha256_json({'resume_json': resume_json, 'design_json': design_json, 'revision': revision})


@transaction.atomic
def ensure_studio(resume: Resume, user=None) -> tuple[ResumeDraft, ResumeDesignRevision]:
    locked = Resume.objects.select_for_update().select_related('current_version', 'current_design_revision').get(pk=resume.pk)
    if not locked.current_version_id:
        from .versioning import ensure_resume_version
        ensure_resume_version(locked, user=user)
        locked.refresh_from_db()
    design_revision = locked.current_design_revision
    if not design_revision:
        design = default_design(
            template_key=locked.template_name if locked.template_name in {
                'ats-classic', 'modern-professional', 'engineering', 'graduate',
                'management-consulting', 'academic-research',
            } else 'ats-classic',
            language=locked.current_version.language,
        )
        design_revision = ResumeDesignRevision.objects.create(
            resume=locked,
            revision_number=1,
            template_key=design['template_key'],
            template_version=design['template_version'],
            language=design['language'],
            page_size=design['page_size'],
            design_json=design,
            design_hash=design_hash(design),
            created_by=user if getattr(user, 'is_authenticated', False) else locked.user,
        )
        locked.current_design_revision = design_revision
        locked.save(update_fields=['current_design_revision', 'updated_at'])
    draft = ResumeDraft.objects.filter(resume=locked).first()
    if not draft:
        resume_json = validate_resume(locked.current_version.resume_json)
        design_json = validate_design(design_revision.design_json)
        draft = ResumeDraft.objects.create(
            resume=locked,
            base_version=locked.current_version,
            resume_json=resume_json,
            design_json=design_json,
            revision=1,
            etag=etag_for(resume_json, design_json, 1),
            updated_by=user if getattr(user, 'is_authenticated', False) else locked.user,
        )
    return draft, design_revision


@transaction.atomic
def update_draft(*, resume: Resume, user, if_match: str, resume_json=None, design_json=None) -> ResumeDraft:
    draft, _ = ensure_studio(resume, user)
    draft = ResumeDraft.objects.select_for_update().get(pk=draft.pk)
    normalized_match = (if_match or '').strip().strip('"')
    if not normalized_match or normalized_match != draft.etag:
        exc = VersionConflict()
        exc.detail = {
            'code': 'version_conflict',
            'detail': str(exc.default_detail),
            'current_etag': draft.etag,
            'current_revision': draft.revision,
        }
        raise exc
    if resume_json is not None:
        draft.resume_json = validate_resume(resume_json)
    if design_json is not None:
        draft.design_json = validate_design(design_json)
    draft.revision += 1
    draft.etag = etag_for(draft.resume_json, draft.design_json, draft.revision)
    draft.updated_by = user
    draft.save()
    return draft


@transaction.atomic
def commit_draft(*, resume: Resume, user, if_match: str, change_summary: str, source: str, evidence_links=None):
    draft, current_design = ensure_studio(resume, user)
    draft = ResumeDraft.objects.select_for_update().select_related('resume', 'base_version').get(pk=draft.pk)
    if (if_match or '').strip().strip('"') != draft.etag:
        raise VersionConflict()
    version = create_resume_version(
        resume=draft.resume,
        resume_json=draft.resume_json,
        user=user,
        source=source,
        change_summary=change_summary,
        parent=draft.base_version,
        evidence_links=evidence_links or [],
        language=draft.design_json.get('language', 'zh-CN'),
    )
    normalized_design = validate_design(draft.design_json)
    new_design_hash = design_hash(normalized_design)
    if current_design.design_hash != new_design_hash:
        next_number = (
            ResumeDesignRevision.objects.filter(resume=draft.resume).aggregate(value=Max('revision_number'))['value'] or 0
        ) + 1
        current_design = ResumeDesignRevision.objects.create(
            resume=draft.resume,
            revision_number=next_number,
            parent=current_design,
            template_key=normalized_design['template_key'],
            template_version=normalized_design['template_version'],
            language=normalized_design['language'],
            page_size=normalized_design['page_size'],
            design_json=normalized_design,
            design_hash=new_design_hash,
            created_by=user,
        )
        draft.resume.current_design_revision = current_design
        draft.resume.save(update_fields=['current_design_revision', 'updated_at'])
    draft.base_version = version
    draft.revision += 1
    draft.etag = etag_for(draft.resume_json, draft.design_json, draft.revision)
    draft.updated_by = user
    draft.save()
    return version, current_design, draft
