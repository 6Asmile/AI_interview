import re
from collections import Counter

import jieba

from .json_resume import json_resume_plain_text


RULE_VERSION = 'ifaceoff-resume-fit/1.0'
STOP_WORDS = {'负责', '相关', '以及', '进行', '能够', '工作', '经验', '要求', '优先', '熟悉', '掌握', '使用'}


def _keywords(text: str) -> list[str]:
    tokens = [token.strip().lower() for token in jieba.lcut(text or '')]
    return [token for token in tokens if len(token) > 1 and token not in STOP_WORDS and re.search(r'[\w\u4e00-\u9fff]', token)]


def calculate_resume_fit(resume_json: dict, jd_text: str, evidence_snapshot: list[dict] | None = None) -> dict:
    resume_text = json_resume_plain_text(resume_json)
    jd_counts = Counter(_keywords(jd_text))
    resume_tokens = set(_keywords(resume_text))
    weighted_total = sum(jd_counts.values()) or 1
    weighted_hit = sum(count for token, count in jd_counts.items() if token in resume_tokens)
    keyword_ratio = min(1.0, weighted_hit / weighted_total)

    basics = resume_json.get('basics') or {}
    parse_fields = [basics.get('name'), basics.get('email') or basics.get('phone'), resume_json.get('work') or resume_json.get('projects')]
    parseability = round(20 * sum(bool(item) for item in parse_fields) / len(parse_fields), 2)
    sections = ('work', 'education', 'projects', 'skills')
    structure = round(15 * sum(bool(resume_json.get(section)) for section in sections) / len(sections), 2)
    keyword = round(25 * keyword_ratio, 2)

    jd_unique = set(jd_counts)
    semantic_overlap = len(jd_unique.intersection(resume_tokens)) / max(1, len(jd_unique))
    semantic = round(25 * min(1.0, semantic_overlap), 2)
    evidence_count = len(evidence_snapshot or [])
    evidence = round(min(15.0, evidence_count * 3.0), 2)
    total = round(parseability + structure + keyword + semantic + evidence, 2)
    missing = [token for token, _ in jd_counts.most_common(30) if token not in resume_tokens][:12]
    return {
        'name': 'iFaceoff Resume Fit',
        'score': total,
        'rule_version': RULE_VERSION,
        'breakdown': {
            'parseability': parseability,
            'structure_completeness': structure,
            'keyword_coverage': keyword,
            'semantic_role_fit': semantic,
            'evidence_quality': evidence,
        },
        'matched_keywords': [token for token, _ in jd_counts.most_common(30) if token in resume_tokens][:20],
        'missing_keywords': missing,
        'disclaimer': '该分数用于 iFaceoff 内部简历与岗位匹配分析，不代表任何第三方 ATS 的通过概率。',
    }

