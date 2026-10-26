from __future__ import annotations

from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from careers.models import CareerFact

from .json_resume import JSON_RESUME_SCHEMA_VERSION, legacy_resume_to_json_resume, normalize_json_resume
from .models import Resume, ResumeDraft, ResumeEvidenceLink, ResumeSuggestion, ResumeVariant, ResumeVersion
from .schema import sha256_json, validate_resume


def _confirmed_fact_snapshot(user, fact_ids: list[int] | None = None) -> list[dict]:
    facts = CareerFact.objects.filter(user=user, verification_status=CareerFact.VerificationStatus.CONFIRMED)
    if fact_ids is not None:
        facts = facts.filter(id__in=fact_ids)
    return [
        {
            'id': fact.id,
            'type': fact.fact_type,
            'title': fact.title,
            'source_type': fact.source_type,
            'source_url': fact.source_url,
            'verified_at': fact.verified_at.isoformat() if fact.verified_at else None,
        }
        for fact in facts.order_by('id')
    ]


@transaction.atomic
def create_resume_version(
    *,
    resume: Resume,
    resume_json: dict | None,
    layout_json: dict | None = None,
    user=None,
    source: str = ResumeVersion.Source.EDITOR,
    change_summary: str = '',
    parent: ResumeVersion | None = None,
    evidence_fact_ids: list[int] | None = None,
    evidence_links: list[dict] | None = None,
    language: str = 'zh-CN',
    activate: bool = True,
) -> ResumeVersion:
    locked = Resume.objects.select_for_update().get(pk=resume.pk)
    next_number = (locked.versions.aggregate(value=Max('version_number'))['value'] or 0) + 1
    parent = parent or locked.current_version
    normalized = validate_resume(resume_json)
    version = ResumeVersion.objects.create(
        resume=locked,
        version_number=next_number,
        parent=parent,
        schema_version=JSON_RESUME_SCHEMA_VERSION,
        resume_json=normalized,
        content_hash=sha256_json(normalized),
        language=language if language in {'zh-CN', 'en-US'} else 'zh-CN',
        layout_json=layout_json or {},
        # Legacy snapshot stays empty for new writes. Evidence now lives in
        # pointer-level ResumeEvidenceLink records.
        evidence_snapshot=[],
        source=source,
        change_summary=change_summary[:255],
        created_by=user if getattr(user, 'is_authenticated', False) else locked.user,
    )
    if activate:
        locked.current_version = version
        locked.canonical_schema_version = JSON_RESUME_SCHEMA_VERSION
        locked.save(update_fields=['current_version', 'canonical_schema_version', 'updated_at'])
        resume.current_version = version
    requested_links = list(evidence_links or [])
    requested_links.extend(
        {'json_pointer': '/', 'fact_id': fact_id}
        for fact_id in (evidence_fact_ids or [])
    )
    if requested_links:
        fact_ids = {int(item['fact_id']) for item in requested_links}
        facts = {
            fact.id: fact
            for fact in CareerFact.objects.filter(
                user=locked.user,
                id__in=fact_ids,
                verification_status=CareerFact.VerificationStatus.CONFIRMED,
            )
        }
        if set(facts) != fact_ids:
            raise ValidationError({'evidence_links': '只能关联当前用户已确认的职业事实。'})
        for item in requested_links:
            pointer = str(item.get('json_pointer') or '/')
            if not pointer.startswith('/') or len(pointer) > 500:
                raise ValidationError({'evidence_links': f'无效 JSON Pointer: {pointer}'})
            fact = facts[int(item['fact_id'])]
            snapshot = {
                'id': fact.id,
                'type': fact.fact_type,
                'title': fact.title,
                'organization': fact.organization,
                'role': fact.role,
                'description': fact.description,
                'skills': fact.skills,
                'metrics': fact.metrics,
                'source_type': fact.source_type,
                'source_url': fact.source_url,
                'verified_at': fact.verified_at.isoformat() if fact.verified_at else None,
            }
            ResumeEvidenceLink.objects.create(
                resume_version=version,
                json_pointer=pointer,
                career_fact=fact,
                fact_snapshot=snapshot,
                fact_hash=sha256_json(snapshot),
            )
    draft = ResumeDraft.objects.select_for_update().filter(resume=locked).first()
    if draft and activate:
        draft.base_version = version
        draft.resume_json = normalized
        draft.revision += 1
        draft.etag = sha256_json({
            'resume_json': draft.resume_json,
            'design_json': draft.design_json,
            'revision': draft.revision,
        })
        draft.updated_by = user if getattr(user, 'is_authenticated', False) else locked.user
        draft.save()
    return version


def ensure_resume_version(resume: Resume, user=None) -> ResumeVersion:
    if resume.current_version_id:
        return resume.current_version
    return create_resume_version(
        resume=resume,
        resume_json=legacy_resume_to_json_resume(resume),
        layout_json=resume.content_json or {},
        user=user or resume.user,
        source=ResumeVersion.Source.LEGACY_MIGRATION,
        change_summary='从旧版简历结构生成初始版本',
    )


def _decode_pointer(path: str) -> list[str]:
    if path == '':
        return []
    if not path.startswith('/'):
        raise ValidationError({'patch': f'无效 JSON Pointer: {path}'})
    return [part.replace('~1', '/').replace('~0', '~') for part in path[1:].split('/')]


def apply_json_patch(document: dict, operations: list[dict]) -> dict:
    result = deepcopy(document)
    if not isinstance(operations, list) or len(operations) > 100:
        raise ValidationError({'patch': 'patch 必须是最多 100 条操作的数组。'})
    for operation in operations:
        if not isinstance(operation, dict) or operation.get('op') not in {'add', 'replace', 'remove'}:
            raise ValidationError({'patch': '仅支持 add、replace、remove 操作。'})
        parts = _decode_pointer(str(operation.get('path', '')))
        if not parts:
            raise ValidationError({'patch': '禁止替换整个简历根对象。'})
        target = result
        for part in parts[:-1]:
            if isinstance(target, list):
                try:
                    target = target[int(part)]
                except (ValueError, IndexError):
                    raise ValidationError({'patch': f'路径不存在: {operation.get("path")}'})
            elif isinstance(target, dict) and part in target:
                target = target[part]
            else:
                raise ValidationError({'patch': f'路径不存在: {operation.get("path")}'})
        key = parts[-1]
        op = operation['op']
        if isinstance(target, list):
            if key == '-' and op == 'add':
                target.append(deepcopy(operation.get('value')))
                continue
            try:
                index = int(key)
            except ValueError:
                raise ValidationError({'patch': f'数组索引无效: {key}'})
            if op == 'add':
                if index < 0 or index > len(target):
                    raise ValidationError({'patch': f'数组索引越界: {index}'})
                target.insert(index, deepcopy(operation.get('value')))
            elif 0 <= index < len(target):
                if op == 'remove':
                    target.pop(index)
                else:
                    target[index] = deepcopy(operation.get('value'))
            else:
                raise ValidationError({'patch': f'数组索引越界: {index}'})
        elif isinstance(target, dict):
            if op in {'replace', 'remove'} and key not in target:
                raise ValidationError({'patch': f'路径不存在: {operation.get("path")}'})
            if op == 'remove':
                target.pop(key)
            else:
                target[key] = deepcopy(operation.get('value'))
        else:
            raise ValidationError({'patch': f'目标不可编辑: {operation.get("path")}'})
    return normalize_json_resume(result)


@transaction.atomic
def accept_suggestion(suggestion: ResumeSuggestion, user) -> ResumeVersion:
    suggestion = ResumeSuggestion.objects.select_for_update().select_related(
        'resume', 'base_version', 'job_target',
    ).get(pk=suggestion.pk)
    if suggestion.resume.user_id != user.id:
        raise ValidationError('无权处理该建议。')
    if suggestion.status != ResumeSuggestion.Status.PENDING:
        raise ValidationError('该建议已经处理。')
    current = suggestion.resume.current_version or suggestion.base_version
    if current.id != suggestion.base_version_id:
        raise ValidationError('简历版本已变化，请重新生成建议。')
    patched = apply_json_patch(current.resume_json, suggestion.patch)
    is_job_variant = suggestion.task_key == 'resume.jd_tailor' and suggestion.job_target_id
    version = create_resume_version(
        resume=suggestion.resume,
        resume_json=patched,
        layout_json=current.layout_json,
        user=user,
        source=ResumeVersion.Source.JD_VARIANT if is_job_variant else ResumeVersion.Source.AI_SUGGESTION,
        change_summary=suggestion.summary,
        parent=current,
        evidence_links=suggestion.evidence_links or [
            {'json_pointer': '/', 'fact_id': fact_id}
            for fact_id in suggestion.evidence_fact_ids
        ],
        activate=not is_job_variant,
    )
    if is_job_variant:
        ResumeVariant.objects.create(
            user=user,
            resume=suggestion.resume,
            source_version=current,
            version=version,
            job_target=suggestion.job_target,
            title=f'{suggestion.job_target.company_name} · {suggestion.job_target.position_name}',
        )
    suggestion.status = ResumeSuggestion.Status.ACCEPTED
    suggestion.accepted_version = version
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=['status', 'accepted_version', 'decided_at'])
    return version
