from __future__ import annotations

from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from careers.models import CareerFact

from .json_resume import JSON_RESUME_SCHEMA_VERSION, legacy_resume_to_json_resume, normalize_json_resume
from .models import Resume, ResumeSuggestion, ResumeVersion


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
) -> ResumeVersion:
    locked = Resume.objects.select_for_update().get(pk=resume.pk)
    next_number = (locked.versions.aggregate(value=Max('version_number'))['value'] or 0) + 1
    parent = parent or locked.current_version
    version = ResumeVersion.objects.create(
        resume=locked,
        version_number=next_number,
        parent=parent,
        schema_version=JSON_RESUME_SCHEMA_VERSION,
        resume_json=normalize_json_resume(resume_json),
        layout_json=layout_json or {},
        evidence_snapshot=_confirmed_fact_snapshot(locked.user, evidence_fact_ids),
        source=source,
        change_summary=change_summary[:255],
        created_by=user if getattr(user, 'is_authenticated', False) else locked.user,
    )
    locked.current_version = version
    locked.canonical_schema_version = JSON_RESUME_SCHEMA_VERSION
    locked.save(update_fields=['current_version', 'canonical_schema_version', 'updated_at'])
    resume.current_version = version
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
    suggestion = ResumeSuggestion.objects.select_for_update().select_related('resume', 'base_version').get(pk=suggestion.pk)
    if suggestion.resume.user_id != user.id:
        raise ValidationError('无权处理该建议。')
    if suggestion.status != ResumeSuggestion.Status.PENDING:
        raise ValidationError('该建议已经处理。')
    current = suggestion.resume.current_version or suggestion.base_version
    if current.id != suggestion.base_version_id:
        raise ValidationError('简历版本已变化，请重新生成建议。')
    patched = apply_json_patch(current.resume_json, suggestion.patch)
    version = create_resume_version(
        resume=suggestion.resume,
        resume_json=patched,
        layout_json=current.layout_json,
        user=user,
        source=ResumeVersion.Source.AI_SUGGESTION,
        change_summary=suggestion.summary,
        parent=current,
        evidence_fact_ids=suggestion.evidence_fact_ids,
    )
    suggestion.status = ResumeSuggestion.Status.ACCEPTED
    suggestion.accepted_version = version
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=['status', 'accepted_version', 'decided_at'])
    return version

