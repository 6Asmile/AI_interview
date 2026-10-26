from __future__ import annotations

import json
import re

from careers.models import CareerFact, JobTarget
from interviews.configuration import (
    BASELINE_PROMPTS,
    render_prompt_source,
    render_registered_prompt,
    resolve_agent_config,
    validate_prompt_output,
)
from system.model_gateway import ModelGateway

from .models import ResumeSuggestion, ResumeVersion
from .schema import sha256_json
from .versioning import apply_json_patch


RESUME_TASK_KEYS = {
    'resume.from_career_facts',
    'resume.rewrite_section',
    'resume.achievement_coach',
    'resume.quality_review',
    'resume.jd_tailor',
}
METRIC_PATTERN = re.compile(r'(?<!\w)(?:\d+(?:\.\d+)?%?|\d+\s*(?:万|亿|k|m|ms|qps))(?!\w)', re.IGNORECASE)


def _context_item(item_type, source, trust_level, content, revision_ids):
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    return {
        'type': item_type,
        'source': source,
        'trust_level': trust_level,
        'content': content,
        'token_count': max(1, len(raw) // 4),
        'revision_ids': [str(value) for value in revision_ids if value],
    }


def build_resume_context(*, version: ResumeVersion, task_key: str, instruction: str = '', job_target=None):
    facts = list(CareerFact.objects.filter(
        user=version.resume.user,
        verification_status=CareerFact.VerificationStatus.CONFIRMED,
    ).values(
        'id', 'fact_type', 'title', 'organization', 'role', 'description',
        'start_date', 'end_date', 'skills', 'metrics', 'source_type', 'source_url',
    ))
    revision_ids = [version.pk]
    envelope = {
        'policy_context': [_context_item(
            'resume_safety_policy',
            'code',
            'system',
            {
                'facts_only': True,
                'patch_only': True,
                'forbid_invented_experience': True,
                'forbid_unverified_metrics': True,
            },
            revision_ids,
        )],
        'task_context': [_context_item(
            'resume_task',
            'request',
            'untrusted_user_input',
            {'task_key': task_key, 'instruction': instruction[:4000]},
            revision_ids,
        )],
        'conversation_context': [],
        'memory_context': [],
        'evidence_context': [
            _context_item('resume_snapshot', 'ResumeVersion', 'untrusted_document', version.resume_json, revision_ids),
            _context_item('confirmed_career_facts', 'CareerFact', 'verified_user_fact', facts, revision_ids),
        ],
        'control_context': [_context_item(
            'output_control',
            'code',
            'system',
            {'base_version_id': version.pk, 'json_patch_only': True},
            revision_ids,
        )],
        'metadata': {
            'resume_id': version.resume_id,
            'resume_version_id': version.pk,
            'content_hash': version.content_hash,
            'task_key': task_key,
        },
    }
    if job_target:
        envelope['evidence_context'].append(_context_item(
            'job_description',
            'JobTarget',
            'untrusted_document',
            {
                'id': job_target.pk,
                'company_name': job_target.company_name,
                'position_name': job_target.position_name,
                'jd_text': job_target.jd_text[:30000],
                'jd_snapshot_hash': job_target.jd_snapshot_hash,
            },
            revision_ids,
        ))
        envelope['metadata']['job_target_id'] = job_target.pk
    envelope['metadata']['envelope_hash'] = sha256_json(envelope)
    envelope['metadata']['region_tokens'] = {
        key: sum(item['token_count'] for item in value)
        for key, value in envelope.items()
        if isinstance(value, list)
    }
    return envelope


def _render_resume_prompt(snapshot, task_key, envelope):
    variables = {'context_json': json.dumps(envelope, ensure_ascii=False, default=str)}
    registered = render_registered_prompt(snapshot, task_key, variables)
    if registered:
        return registered
    baseline = BASELINE_PROMPTS[task_key]
    system_message, user_message, metadata = render_prompt_source(
        system_template=baseline['system_template'],
        user_template=baseline['user_template'],
        variable_schema={
            'type': 'object',
            'properties': {'context_json': {'type': 'string'}},
            'required': ['context_json'],
        },
        variables=variables,
    )
    return [
        {'role': 'system', 'content': system_message},
        {'role': 'user', 'content': user_message},
    ], {
        **metadata,
        'task_key': task_key,
        'prompt_hash': sha256_json(baseline),
        'model_alias': '',
        'temperature': baseline['temperature'],
        'max_output_tokens': baseline['max_output_tokens'],
        'output_contract': baseline['output_contract'],
    }


def _coerce_patch(task_key, result):
    patch = result.get('patch') or result.get('candidate_patch') or []
    if task_key == 'resume.from_career_facts' and isinstance(result.get('resume_json'), dict):
        generated = result['resume_json']
        patch = [
            {'op': 'add', 'path': f'/{key}', 'value': value}
            for key, value in generated.items()
            if key not in {'meta', 'x-ifaceoff'}
        ]
    return patch if isinstance(patch, list) else []


def _validate_evidence_and_metrics(*, user, patch, evidence_links):
    links = evidence_links if isinstance(evidence_links, list) else []
    fact_ids = {
        int(item.get('fact_id') or item.get('career_fact_id'))
        for item in links
        if isinstance(item, dict) and (item.get('fact_id') is not None or item.get('career_fact_id') is not None)
    }
    confirmed = set(CareerFact.objects.filter(
        user=user,
        id__in=fact_ids,
        verification_status=CareerFact.VerificationStatus.CONFIRMED,
    ).values_list('id', flat=True))
    if confirmed != fact_ids:
        raise ValueError('suggestion_unconfirmed_evidence')
    evidence_paths = {
        str(item.get('json_pointer') or '')
        for item in links
        if isinstance(item, dict) and (item.get('fact_id') is not None or item.get('career_fact_id') is not None)
    }
    for operation in patch:
        value = json.dumps(operation.get('value'), ensure_ascii=False, default=str)
        path = str(operation.get('path') or '')
        if METRIC_PATTERN.search(value) and not any(
            path == pointer or path.startswith(pointer + '/') or pointer.startswith(path + '/')
            for pointer in evidence_paths
        ):
            raise ValueError(f'suggestion_metric_without_evidence:{path}')
    return sorted(fact_ids)


def generate_resume_suggestion(*, version, task_key, instruction='', job_target_id=None):
    if task_key not in RESUME_TASK_KEYS:
        raise ValueError('unsupported_resume_task')
    job_target = None
    if job_target_id:
        job_target = JobTarget.objects.filter(pk=job_target_id, user=version.resume.user).first()
        if not job_target:
            raise ValueError('job_target_not_found')
    if task_key == 'resume.jd_tailor' and not job_target:
        raise ValueError('job_target_required')
    snapshot = resolve_agent_config()
    envelope = build_resume_context(
        version=version,
        task_key=task_key,
        instruction=instruction,
        job_target=job_target,
    )
    messages, prompt_metadata = _render_resume_prompt(snapshot, task_key, envelope)
    result = ModelGateway(version.resume.user).chat_json(
        messages,
        max_tokens=int(prompt_metadata.get('max_output_tokens', 1600)),
        temperature=float(prompt_metadata.get('temperature', 0.1)),
        alias_slug=prompt_metadata.get('model_alias') or 'chat.default',
    )
    validate_prompt_output(result, prompt_metadata.get('output_contract'))
    patch = _coerce_patch(task_key, result)
    evidence_links = result.get('evidence_links') or []
    fact_ids = _validate_evidence_and_metrics(
        user=version.resume.user,
        patch=patch,
        evidence_links=evidence_links,
    )
    evidence_links = [
        {
            'json_pointer': str(item.get('json_pointer') or '/'),
            'fact_id': int(item.get('fact_id') or item.get('career_fact_id')),
        }
        for item in evidence_links
        if isinstance(item, dict) and (item.get('fact_id') is not None or item.get('career_fact_id') is not None)
    ]
    if patch:
        apply_json_patch(version.resume_json, patch)
        suggestion = ResumeSuggestion.objects.create(
            resume=version.resume,
            base_version=version,
            patch=patch,
            summary=str(result.get('summary') or result.get('rationale') or 'AI 简历建议')[:255],
            rationale=str(result.get('rationale') or ''),
            evidence_fact_ids=fact_ids,
            evidence_links=evidence_links,
            task_key=task_key,
            job_target=job_target,
            created_by=version.resume.user,
        )
    else:
        suggestion = None
    return {
        'suggestion': suggestion,
        'questions': result.get('questions') or [],
        'missing_evidence': result.get('missing_evidence') or result.get('unmatched_requirements') or [],
        'prompt_hash': prompt_metadata.get('prompt_hash', ''),
        'config_hash': snapshot.get('config_hash', ''),
        'envelope_hash': envelope['metadata']['envelope_hash'],
        'region_tokens': envelope['metadata']['region_tokens'],
    }
