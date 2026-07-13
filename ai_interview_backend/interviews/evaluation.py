import hashlib
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from users.models import User

from .models import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunMetric,
    InterviewRubric,
    InterviewTemplate,
    InterviewTemplateStage,
    RubricDimension,
    RubricLevelAnchor,
)


DEFAULT_DIMENSIONS = [
    ('relevance', '岗位相关性', '回答是否切中问题和岗位要求', 1.1),
    ('clarity', '沟通表达', '结构、逻辑和表达清晰度', 1.0),
    ('depth', '技术/业务深度', '原理、方案、取舍和边界的深度', 1.2),
    ('evidence', '证据与量化结果', '真实案例、个人贡献、指标和结果验证', 1.2),
    ('star', 'STAR完整度', '场景、任务、行动、结果是否完整', 0.8),
]

DEFAULT_STAGES = [
    ('opening', '开场定位', 1, Decimal('0.05'), ['relevance', 'clarity']),
    ('self_intro', '自我介绍', 2, Decimal('0.08'), ['relevance', 'clarity']),
    ('project_anchor', '项目定位', 3, Decimal('0.10'), ['evidence', 'star']),
    ('project_deep_dive', '项目深挖', 4, Decimal('0.22'), ['depth', 'evidence']),
    ('fundamentals_probe', '基础知识验证', 5, Decimal('0.16'), ['depth', 'relevance']),
    ('role_specific', '岗位专项', 6, Decimal('0.14'), ['depth', 'evidence']),
    ('system_design', '系统设计', 7, Decimal('0.12'), ['depth', 'relevance']),
    ('behavioral', '行为面试', 8, Decimal('0.08'), ['clarity', 'star']),
    ('candidate_questions', '候选人反问', 9, Decimal('0.05'), ['clarity']),
]


def can_manage_interview_system(user: User) -> bool:
    return bool(user and getattr(user, 'is_authenticated', False) and (
        user.is_staff or user.role in (User.Role.ADMIN, User.Role.HR)
    ))


@transaction.atomic
def ensure_default_interview_assets(created_by=None) -> dict:
    rubric, _ = InterviewRubric.objects.get_or_create(
        name='系统通用企业面试量表',
        visibility=InterviewRubric.Visibility.SYSTEM,
        defaults={
            'description': '覆盖岗位相关性、表达、深度、证据和STAR结构的企业通用量表。',
            'created_by': created_by,
        }
    )
    for order, (key, name, description, weight) in enumerate(DEFAULT_DIMENSIONS, start=1):
        dimension, _ = RubricDimension.objects.get_or_create(
            rubric=rubric,
            key=key,
            defaults={
                'name': name,
                'description': description,
                'weight': Decimal(str(weight)),
                'min_coverage': 1,
                'order': order,
                'rule_config': {},
            }
        )
        if not dimension.anchors.exists():
            anchors = [
                ('weak', 0, 49, '缺少与问题直接相关的有效信息，难以支持能力判断。'),
                ('average', 50, 69, '回答基本相关，但证据、深度或结构仍不充分。'),
                ('solid', 70, 84, '回答清楚且有一定证据，能够支持主要能力判断。'),
                ('strong', 85, 100, '回答具体、深入、有量化结果，并体现清晰取舍和复盘。'),
            ]
            RubricLevelAnchor.objects.bulk_create([
                RubricLevelAnchor(dimension=dimension, level=level, min_score=low, max_score=high, description=text)
                for level, low, high, text in anchors
            ])

    templates = {}
    for name, keywords, description in [
        ('通用技术岗位模板', [], '适用于大多数技术岗位的项目深挖和能力验证流程。'),
        ('AI 应用开发模板', ['ai应用', '大模型', 'rag', 'agent', 'mcp', 'langgraph'], '面向 AI 应用、RAG、Agent 与企业大模型落地岗位。'),
        ('JD 定制模板', ['jd_custom'], '根据 JD 自动抽取职责、技能和业务场景的模板。'),
    ]:
        template, _ = InterviewTemplate.objects.get_or_create(
            name=name,
            visibility=InterviewTemplate.Visibility.SYSTEM,
            defaults={
                'description': description,
                'job_keywords': keywords,
                'rubric': rubric,
                'created_by': created_by,
                'config': {'final_gap_strategy': 'highest_weight_uncovered'},
            }
        )
        default_stage_keys = []
        for stage_key, stage_name, order, ratio, dimensions in DEFAULT_STAGES:
            default_stage_keys.append(stage_key)
            InterviewTemplateStage.objects.update_or_create(
                template=template,
                stage_key=stage_key,
                defaults={
                    'name': stage_name,
                    'order': order,
                    'question_ratio': ratio,
                    'target_dimensions': dimensions,
                    'question_guidance': f'围绕{stage_name}验证候选人的真实经历、个人贡献和结果证据。',
                },
            )
        template.stages.exclude(stage_key__in=default_stage_keys).delete()
        templates[template.name] = template
    return {'rubric': rubric, 'templates': templates}


def _visible_template_queryset(user=None):
    queryset = InterviewTemplate.objects.filter(is_active=True)
    public_filter = Q(visibility__in=[InterviewTemplate.Visibility.SYSTEM, InterviewTemplate.Visibility.SHARED])
    if can_manage_interview_system(user):
        return queryset
    if user and getattr(user, 'is_authenticated', False):
        return queryset.filter(public_filter | Q(created_by=user))
    return queryset.filter(public_filter)


def select_interview_template(job_position: str, jd_text: str = '', template_id=None, user=None) -> InterviewTemplate:
    ensure_default_interview_assets()
    queryset = _visible_template_queryset(user)
    if template_id:
        return queryset.get(id=template_id)
    source = ' '.join(filter(None, [job_position, jd_text])).lower()
    if jd_text:
        return queryset.filter(name='JD 定制模板').first()
    for template in queryset.order_by('visibility', '-updated_at'):
        if any(str(keyword).lower() in source for keyword in template.job_keywords or []):
            return template
    return queryset.filter(name='通用技术岗位模板').first()


def build_template_snapshot(template: InterviewTemplate) -> dict:
    dimensions = [
        {
            'key': dim.key,
            'name': dim.name,
            'description': dim.description,
            'weight': float(dim.weight),
            'min_coverage': dim.min_coverage,
            'anchors': [
                {
                    'level': anchor.level,
                    'min_score': anchor.min_score,
                    'max_score': anchor.max_score,
                    'description': anchor.description,
                }
                for anchor in dim.anchors.all()
            ],
        }
        for dim in template.rubric.dimensions.all().order_by('order', 'id')
    ]
    stages = [
        {
            'stage_key': stage.stage_key,
            'name': stage.name,
            'order': stage.order,
            'question_ratio': float(stage.question_ratio),
            'target_dimensions': stage.target_dimensions,
            'question_guidance': stage.question_guidance,
            'min_duration_minutes': stage.min_duration_minutes,
            'max_duration_minutes': stage.max_duration_minutes,
            'min_verified_dimensions': stage.min_verified_dimensions,
            'allowed_question_types': stage.allowed_question_types,
            'entry_condition': stage.entry_condition,
            'exit_condition': stage.exit_condition,
            'allow_topic_return': stage.allow_topic_return,
        }
        for stage in template.stages.all().order_by('order', 'id')
    ]
    return {
        'template_id': template.id,
        'template_name': template.name,
        'template_version': template.version,
        'require_rag': template.require_rag,
        'interview_mode': template.interview_mode,
        'target_duration_minutes': template.target_duration_minutes,
        'min_duration_minutes': template.min_duration_minutes,
        'hard_max_duration_minutes': template.hard_max_duration_minutes,
        'min_turns': template.min_turns,
        'max_turns': template.max_turns,
        'candidate_question_minutes': template.candidate_question_minutes,
        'style_profile': template.style_profile,
        'rubric_id': template.rubric_id,
        'rubric_name': template.rubric.name,
        'rubric_version': template.rubric.version,
        'dimensions': dimensions,
        'stages': stages,
        'config': template.config,
    }


def build_session_plan(
    template: InterviewTemplate,
    question_count: int,
    job_position: str,
    jd_text: str = '',
    target_duration_minutes: int | None = None,
    interview_mode: str = '',
    experience_mode: str = 'realistic',
) -> tuple[dict, dict]:
    snapshot = build_template_snapshot(template)
    stages = snapshot['stages']
    stage_plan = []
    allocated = 0
    for index, stage in enumerate(stages):
        if index == len(stages) - 1:
            count = max(0, question_count - allocated)
        else:
            count = max(1 if index == 0 else 0, round(question_count * stage['question_ratio']))
        allocated += count
        stage_plan.append({**stage, 'question_count': count})
    plan = {
        'job_position': job_position,
        'jd_hash': hashlib.sha256((jd_text or '').encode('utf-8')).hexdigest()[:16] if jd_text else '',
        'question_count': question_count,
        'estimated_question_range': {'min': snapshot['min_turns'], 'max': snapshot['max_turns']},
        'interview_mode': interview_mode or snapshot['interview_mode'],
        'experience_mode': experience_mode,
        'style_profile': snapshot['style_profile'],
        'termination_policy': {
            'target_duration_minutes': int(target_duration_minutes or snapshot['target_duration_minutes']),
            'min_duration_minutes': snapshot['min_duration_minutes'],
            'hard_max_duration_minutes': max(
                int(target_duration_minutes or snapshot['target_duration_minutes']),
                snapshot['hard_max_duration_minutes'],
            ),
            'min_turns': snapshot['min_turns'],
            'max_turns': snapshot['max_turns'],
            'candidate_question_minutes': snapshot['candidate_question_minutes'],
            'progress_mode': 'time_and_coverage',
        },
        'stage_plan': stage_plan,
        'dimensions': snapshot['dimensions'],
        'coverage_requirements': {
            dim['key']: {'name': dim['name'], 'min_coverage': dim['min_coverage'], 'weight': dim['weight']}
            for dim in snapshot['dimensions']
        },
        'coverage': {},
        'coverage_gaps': [dim['key'] for dim in snapshot['dimensions']],
        'created_at': timezone.now().isoformat(),
    }
    return plan, snapshot


def _plain_text(value: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value or '')).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def rule_evaluate_answer(question: str, answer: str, session_plan: dict | None = None, target_dimension: str = '') -> dict:
    answer_text = _plain_text(answer)
    question_text = _plain_text(question)
    length = len(answer_text)
    has_numbers = bool(re.search(r'\d+|百分之|提升|降低|增长|减少|ms|秒|分钟|qps|并发', answer_text.lower()))
    has_first_person = _contains_any(answer_text, ['我', '本人', '负责', '主导', '参与'])
    has_tradeoff = _contains_any(answer_text, ['取舍', '权衡', '为什么', '因为', '方案', '对比', '边界', '风险'])
    star_parts = {
        'situation': _contains_any(answer_text, ['背景', '场景', '当时', '项目']),
        'task': _contains_any(answer_text, ['目标', '任务', '需求', '问题']),
        'action': _contains_any(answer_text, ['我', '负责', '设计', '实现', '推动', '优化']),
        'result': _contains_any(answer_text, ['结果', '提升', '降低', '上线', '指标', '数据']),
    }
    question_tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', question_text.lower()))
    answer_tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', answer_text.lower()))
    overlap = len(question_tokens & answer_tokens)

    relevance = min(100, 45 + overlap * 8 + (15 if length >= 80 else 0))
    clarity = min(100, 35 + min(length, 180) // 3 + (10 if any(mark in answer for mark in ['首先', '其次', '最后', '第一', '第二']) else 0))
    depth = min(100, 30 + min(length, 260) // 4 + (15 if has_tradeoff else 0))
    evidence = min(100, 25 + min(length, 180) // 5 + (25 if has_numbers else 0) + (10 if has_first_person else 0))
    star = 35 + sum(15 for ok in star_parts.values() if ok)
    if length < 24:
        relevance = min(relevance, 45)
        clarity = min(clarity, 45)
        depth = min(depth, 35)
        evidence = min(evidence, 30)
        star = min(star, 35)

    scores = {
        'relevance': relevance,
        'clarity': clarity,
        'depth': depth,
        'evidence': evidence,
        'star': min(100, star),
    }
    dimensions = (session_plan or {}).get('dimensions') or [{'key': key, 'weight': 1} for key in scores]
    weighted_total = 0
    weight_sum = 0
    for dim in dimensions:
        key = dim.get('key')
        weight = float(dim.get('weight') or 1)
        weighted_total += scores.get(key, 50) * weight
        weight_sum += weight
    rule_score = round(weighted_total / max(weight_sum, 1))

    evidence_items = []
    if has_first_person:
        evidence_items.append({'type': 'personal_contribution', 'quote': _extract_sentence(answer_text, ['我', '负责', '主导']), 'supported': True})
    if has_numbers:
        evidence_items.append({'type': 'metric_result', 'quote': _extract_sentence(answer_text, ['提升', '降低', '增长', '减少', 'qps', 'ms']), 'supported': True})
    if has_tradeoff:
        evidence_items.append({'type': 'technical_tradeoff', 'quote': _extract_sentence(answer_text, ['取舍', '权衡', '方案', '边界']), 'supported': True})

    risk_flags = []
    if length < 24:
        risk_flags.append('answer_too_short')
    if evidence < 55:
        risk_flags.append('insufficient_evidence')
    if depth < 55:
        risk_flags.append('insufficient_depth')

    return {
        'rule_score': rule_score,
        'rubric_scores': [
            {'dimension_key': key, 'score': int(score), 'reason': _score_reason(key, score)}
            for key, score in scores.items()
        ],
        'evidence_items': evidence_items,
        'star_breakdown': star_parts,
        'risk_flags': risk_flags,
        'confidence': 0.85 if length >= 80 else 0.62,
    }


def _extract_sentence(text: str, hints: list[str]) -> str:
    sentences = re.split(r'[。！？!?；;]\s*', text)
    for sentence in sentences:
        if any(hint.lower() in sentence.lower() for hint in hints):
            return sentence[:180]
    return text[:180]


def _score_reason(key: str, score: int) -> str:
    label = '较弱' if score < 50 else '一般' if score < 70 else '扎实' if score < 85 else '优秀'
    return f'{key} 规则评分为{label}，基于回答长度、问题相关性、证据和结构完整度计算。'


def combine_rule_and_ai_evaluation(rule_result: dict, ai_result: dict | None) -> dict:
    ai_result = ai_result or {}
    ai_score = ai_result.get('quality_score')
    try:
        ai_score = int(ai_score)
    except (TypeError, ValueError):
        ai_score = None
    rule_score = int(rule_result.get('rule_score') or 0)
    if ai_score is None:
        final_score = rule_score
        evaluation_mode = 'rule_only_degraded'
        degraded_reason = 'ai_score_unavailable'
    else:
        final_score = round(rule_score * 0.7 + ai_score * 0.3)
        evaluation_mode = 'rule_ai_dual'
        degraded_reason = ''
    answer_level = (
        'strong' if final_score >= 85 else
        'solid' if final_score >= 70 else
        'average' if final_score >= 50 else
        'weak'
    )
    return {
        **ai_result,
        **rule_result,
        'ai_score': ai_score,
        'quality_score': final_score,
        'final_score': final_score,
        'answer_level': answer_level,
        'evaluation_mode': evaluation_mode,
        'degraded_reason': degraded_reason,
        'unsupported_claim': False,
    }


def update_session_coverage(session, evaluation: dict, question_plan: dict | None = None) -> dict:
    plan = session.session_plan or {}
    coverage = plan.get('coverage') or {}
    target_dimension = (question_plan or {}).get('target_dimension') or (question_plan or {}).get('target')
    dimension_keys = {dim.get('key') for dim in plan.get('dimensions') or []}
    for score_item in evaluation.get('rubric_scores') or []:
        key = score_item.get('dimension_key')
        if key in dimension_keys and int(score_item.get('score') or 0) >= 60:
            coverage[key] = coverage.get(key, 0) + 1
    if target_dimension in dimension_keys:
        coverage[target_dimension] = coverage.get(target_dimension, 0) + 1

    requirements = plan.get('coverage_requirements') or {}
    gaps = [
        key for key, requirement in requirements.items()
        if coverage.get(key, 0) < int(requirement.get('min_coverage') or 1)
    ]
    summary = {
        'coverage': coverage,
        'coverage_gaps': gaps,
        'covered_dimensions': [key for key in requirements if key not in gaps],
        'updated_at': timezone.now().isoformat(),
    }
    plan['coverage'] = coverage
    plan['coverage_gaps'] = gaps
    session.session_plan = plan
    session.coverage_summary = summary
    session.save(update_fields=['session_plan', 'coverage_summary', 'updated_at'])
    return summary


def update_session_coverage_targeted(
    session,
    evaluation: dict,
    question_plan: dict | None = None,
    *,
    confidence_threshold: float = 0.6,
) -> dict:
    """V2 coverage: a question can only verify the dimension it was planned for."""
    plan = session.session_plan or {}
    coverage = dict(plan.get('coverage') or {})
    question_plan = question_plan or {}
    target_dimension = question_plan.get('target_dimension') or ''
    dimensions = {item.get('key'): item for item in plan.get('dimensions') or [] if item.get('key')}
    confidence = float(evaluation.get('confidence') or 0)
    final_score = int(evaluation.get('final_score') or 0)
    supported_evidence = [
        item for item in evaluation.get('evidence_items') or []
        if isinstance(item, dict) and item.get('supported') and item.get('quote')
    ]
    applied = bool(
        target_dimension in dimensions
        and final_score >= 60
        and confidence >= confidence_threshold
        and supported_evidence
        and not evaluation.get('unsupported_claim')
    )
    if applied:
        coverage[target_dimension] = coverage.get(target_dimension, 0) + 1

    requirements = plan.get('coverage_requirements') or {}
    gaps = [
        key for key, requirement in requirements.items()
        if coverage.get(key, 0) < int(requirement.get('min_coverage') or 1)
    ]
    summary = {
        'coverage': coverage,
        'coverage_gaps': gaps,
        'covered_dimensions': [key for key in requirements if key not in gaps],
        'last_target_dimension': target_dimension,
        'last_coverage_applied': applied,
        'last_coverage_reason': '' if applied else 'target_or_evidence_threshold_not_met',
        'updated_at': timezone.now().isoformat(),
    }
    plan['coverage'] = coverage
    plan['coverage_gaps'] = gaps
    session.session_plan = plan
    session.coverage_summary = summary
    session.save(update_fields=['session_plan', 'coverage_summary', 'updated_at'])
    return summary


def validate_generated_question(question_text: str, question_plan: dict, rag_context: list, existing_signatures: set, signature_func) -> list[str]:
    errors = []
    if not question_text.strip():
        errors.append('empty_question')
    if question_text.count('？') + question_text.count('?') > 1:
        errors.append('multiple_questions')
    if signature_func and signature_func(question_text) in existing_signatures:
        errors.append('duplicate_question')
    if question_plan.get('use_rag') and not rag_context:
        errors.append('rag_required_but_empty')
    rag_ids = {str(item.get('chunk_id')) for item in rag_context or [] if item.get('chunk_id')}
    for chunk_id in question_plan.get('rag_source_ids') or []:
        if str(chunk_id) not in rag_ids:
            errors.append('unmatched_rag_source')
            break
    return errors


def summarize_report_scores(history: list, session_plan: dict | None = None) -> dict:
    scores = []
    dimension_totals = {}
    dimension_counts = {}
    for turn in history:
        evaluation = turn.get('evaluation') or turn.get('ai_feedback') or {}
        if evaluation.get('final_score') is not None:
            scores.append(int(evaluation['final_score']))
        for item in evaluation.get('rubric_scores') or []:
            key = item.get('dimension_key')
            dimension_totals[key] = dimension_totals.get(key, 0) + int(item.get('score') or 0)
            dimension_counts[key] = dimension_counts.get(key, 0) + 1
    dimensions = (session_plan or {}).get('dimensions') or []
    ability_scores = []
    for dim in dimensions:
        key = dim.get('key')
        avg = dimension_totals.get(key, 0) / max(dimension_counts.get(key, 0), 1)
        ability_scores.append({'name': dim.get('name') or key, 'score': round(avg / 20, 1), 'raw_score': round(avg)})
    return {
        'overall_score': round(sum(scores) / len(scores)) if scores else 0,
        'ability_scores': ability_scores,
    }


def run_offline_rule_evaluation(run: EvaluationRun) -> EvaluationRun:
    run.status = EvaluationRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=['status', 'started_at'])
    try:
        scores = []
        for case in run.dataset.cases.all():
            rule_result = rule_evaluate_answer(case.question, case.answer, (run.template.config if run.template else {}))
            scores.append(rule_result['rule_score'])
            EvaluationRunMetric.objects.create(
                run=run,
                case=case,
                metric_name='rule_final_score',
                score=rule_result['rule_score'],
                detail=rule_result,
            )
        run.summary = {'case_count': len(scores), 'average_rule_score': round(sum(scores) / max(len(scores), 1), 2)}
        run.status = EvaluationRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=['summary', 'status', 'finished_at'])
        return run
    except Exception as exc:
        run.status = EvaluationRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'finished_at'])
        raise
