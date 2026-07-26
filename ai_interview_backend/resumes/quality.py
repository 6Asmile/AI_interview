from __future__ import annotations

import re
from collections import Counter

from .schema import validation_errors


VAGUE_WORDS = ('负责', '参与', '协助', '熟悉', '了解', 'responsible for', 'helped', 'familiar with')
METRIC_PATTERN = re.compile(r'(?<!\w)(?:\d+(?:\.\d+)?%?|\d+\s*(?:万|亿|k|m|ms|qps))(?!\w)', re.IGNORECASE)


def _issue(code, message, priority='medium', pointer='', source='deterministic'):
    return {'code': code, 'message': message, 'priority': priority, 'pointer': pointer, 'source': source}


def build_quality_report(payload: dict, evidence_pointers: set[str] | None = None) -> dict:
    evidence_pointers = evidence_pointers or set()
    issues = []
    for error in validation_errors(payload):
        issues.append(_issue('schema.invalid', error['message'], 'high', error['pointer']))
    basics = payload.get('basics') or {}
    if not str(basics.get('name') or '').strip():
        issues.append(_issue('required.name', '缺少姓名。', 'high', '/basics/name'))
    if not str(basics.get('summary') or '').strip():
        issues.append(_issue('required.summary', '建议补充 2–4 句职业摘要。', 'medium', '/basics/summary'))
    for section in ('work', 'projects'):
        for index, item in enumerate(payload.get(section) or []):
            pointer = f'/{section}/{index}'
            text = ' '.join([
                str(item.get('summary') or item.get('description') or ''),
                ' '.join(str(value) for value in item.get('highlights') or []),
            ])
            if any(word in text.lower() for word in VAGUE_WORDS):
                issues.append(_issue('content.vague', '表述偏空泛，请说明行动、范围和结果。', 'medium', pointer))
            if len(text) > 1600:
                issues.append(_issue('content.too_long', '单项经历过长，建议压缩到关键职责与成果。', 'medium', pointer))
            if METRIC_PATTERN.search(text) and not any(
                evidence == pointer or evidence.startswith(pointer + '/') for evidence in evidence_pointers
            ):
                issues.append(_issue('evidence.metric_unverified', '存在数字成果但未关联已确认职业事实。', 'high', pointer))
    skills = [
        keyword.strip().lower()
        for item in payload.get('skills') or []
        for keyword in [str(item.get('name') or ''), *(item.get('keywords') or [])]
        if keyword and keyword.strip()
    ]
    duplicates = sorted(key for key, count in Counter(skills).items() if count > 1)
    if duplicates:
        issues.append(_issue('content.duplicate_skills', f'技能重复：{", ".join(duplicates[:10])}', 'low', '/skills'))
    checks = {
        'schema': not any(item['code'].startswith('schema.') for item in issues),
        'ats_reading_order': True,
        'text_layer_required': True,
        'single_column': True,
        'dates': not any(item['code'] == 'schema.invalid' and 'Date' in item['message'] for item in issues),
        'evidence_consistency': not any(item['code'].startswith('evidence.') for item in issues),
    }
    weights = {'high': 12, 'medium': 6, 'low': 2}
    score = max(0, 100 - sum(weights[item['priority']] for item in issues))
    common = sorted(issues, key=lambda item: {'high': 0, 'medium': 1, 'low': 2}[item['priority']])
    return {
        'score': score,
        'checks': checks,
        'issues': common,
        'reviewers': {
            'recruiter': {'focus': ['清晰度', '相关性', '快速扫描'], 'issues': common[:5]},
            'hiring_manager': {'focus': ['职责深度', '影响力', '可信证据'], 'issues': [i for i in common if i['priority'] != 'low'][:5]},
            'domain_reviewer': {'focus': ['技能准确性', '项目复杂度', '可验证成果'], 'issues': [i for i in common if i['code'].startswith(('evidence.', 'content.'))][:5]},
        },
        'consensus': common[:10],
        'ai_review_status': 'not_requested',
    }
