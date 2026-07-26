from __future__ import annotations

import math
import time
from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.response import Response

from interviews.configuration import (
    AgentConfigurationError,
    build_revision_hash,
    render_prompt_source,
    resolve_agent_config_revision,
    stable_hash,
    validate_agent_config_revision,
    validate_ingestion_policy,
    validate_retrieval_config,
)
from interviews.models import (
    AgentConfigEvaluationRun,
    AgentConfigKnowledgeBinding,
    AgentConfigProfile,
    AgentConfigRevision,
    AgentPromptTemplate,
    EvaluationDataset,
)
from knowledge.models import (
    KnowledgeBase,
    KnowledgeBaseRevision,
    KnowledgeBaseRevisionDocument,
    KnowledgeDocument,
    RetrievalProfile,
    RetrievalProfileRevision,
)
from knowledge.services import search_knowledge_context
from system.models import ModelAlias

from .idempotency import run_staff_idempotent
from .operations_views import operation_reason
from .views import StaffProtectedView, audit


def _has_permission(request, permission: str) -> bool:
    permissions = request.user.permission_set()
    return '*' in permissions or permission in permissions


def _forbidden(permission: str) -> Response:
    return Response({
        'code': 'staff_permission_denied',
        'message': f'缺少权限：{permission}',
    }, status=403)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _evaluate_retrieval_dataset(revision: AgentConfigRevision, dataset: EvaluationDataset | None) -> tuple[dict, list]:
    if not dataset:
        return {
            'retrieval_case_count': 0,
            'retrieval_error_count': 0,
            'recall_at_k': None,
            'hit_rate': None,
            'mrr': None,
            'ndcg': None,
            'no_answer_accuracy': None,
            'duplicate_parent_rate': None,
            'topic_hit_rate': None,
            'average_latency_ms': None,
            'p95_latency_ms': None,
            'estimated_rag_tokens': 0,
            'estimated_cost': 0,
        }, []
    snapshot = resolve_agent_config_revision(revision)
    samples = []
    recalls = []
    hits = []
    reciprocal_ranks = []
    ndcgs = []
    no_answer_scores = []
    duplicate_parent_rates = []
    topic_scores = []
    latencies = []
    estimated_tokens = 0
    for case in dataset.cases.all()[:100]:
        started = time.perf_counter()
        error = ''
        try:
            result = search_knowledge_context(
                job_position=case.job_position,
                user=dataset.created_by,
                current_stage='technical_deep_dive',
                pending_topics=case.expected_topics,
                last_evaluation={'follow_up_target': case.expected_follow_up},
                jd_text=case.jd_text,
                limit=10,
                return_trace=True,
                agent_config_snapshot=snapshot,
            )
            contexts = result.get('contexts') or []
            trace = result.get('retrieval_trace') or {}
        except Exception as exc:
            contexts = []
            trace = {'fallback_reason': 'evaluation_retrieval_failed'}
            error = str(exc)[:300]
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        latencies.append(latency_ms)
        retrieved_revisions = [
            str(item.get('document_revision_id') or '')
            for item in contexts
            if item.get('document_revision_id')
        ]
        expected = {str(item) for item in case.expected_document_revision_ids or []}
        irrelevant = {str(item) for item in case.irrelevant_document_revision_ids or []}
        if expected:
            matched = expected.intersection(retrieved_revisions)
            recalls.append(len(matched) / len(expected))
            hits.append(1.0 if matched else 0.0)
            first_rank = next(
                (index for index, revision_id in enumerate(retrieved_revisions, start=1) if revision_id in expected),
                None,
            )
            reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
            dcg = sum(
                1.0 / math.log2(index + 1)
                for index, revision_id in enumerate(retrieved_revisions, start=1)
                if revision_id in expected
            )
            ideal_hits = min(len(expected), len(retrieved_revisions))
            ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
            ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        if case.is_no_answer:
            no_answer_scores.append(1.0 if not contexts else 0.0)
        parents = [
            str(item.get('parent_chunk_id') or item.get('chunk_id') or '')
            for item in contexts
            if item.get('parent_chunk_id') or item.get('chunk_id')
        ]
        duplicate_parent_rates.append(
            (len(parents) - len(set(parents))) / len(parents) if parents else 0.0
        )
        expected_topics = [str(item).lower() for item in case.expected_topics or [] if str(item).strip()]
        if expected_topics:
            joined = '\n'.join(str(item.get('content') or '').lower() for item in contexts)
            topic_scores.append(sum(1 for topic in expected_topics if topic in joined) / len(expected_topics))
        estimated_tokens += sum(int(item.get('token_count') or 0) for item in contexts)
        samples.append({
            'case_id': case.id,
            'retrieved_document_revision_ids': retrieved_revisions,
            'expected_document_revision_ids': sorted(expected),
            'irrelevant_hits': [item for item in retrieved_revisions if item in irrelevant],
            'no_answer': case.is_no_answer,
            'latency_ms': latency_ms,
            'trace': trace,
            'error': error,
        })
    sorted_latencies = sorted(latencies)
    p95_index = max(0, math.ceil(len(sorted_latencies) * 0.95) - 1) if sorted_latencies else 0
    return {
        'retrieval_case_count': len(samples),
        'retrieval_error_count': sum(1 for item in samples if item.get('error')),
        'recall_at_k': _mean(recalls) if recalls else None,
        'hit_rate': _mean(hits) if hits else None,
        'mrr': _mean(reciprocal_ranks) if reciprocal_ranks else None,
        'ndcg': _mean(ndcgs) if ndcgs else None,
        'no_answer_accuracy': _mean(no_answer_scores) if no_answer_scores else None,
        'duplicate_parent_rate': _mean(duplicate_parent_rates) if duplicate_parent_rates else None,
        'topic_hit_rate': _mean(topic_scores) if topic_scores else None,
        'average_latency_ms': _mean(latencies) if latencies else None,
        'p95_latency_ms': sorted_latencies[p95_index] if sorted_latencies else None,
        'estimated_rag_tokens': estimated_tokens,
        'estimated_cost': 0,
    }, samples


def _prompt_payload(prompt: AgentPromptTemplate) -> dict:
    return {
        'id': str(prompt.id),
        'task_key': prompt.task_key,
        'system_template': prompt.system_template,
        'user_template': prompt.user_template,
        'variable_schema': prompt.variable_schema,
        'output_contract': prompt.output_contract,
        'model_alias_id': prompt.model_alias_id,
        'model_alias': prompt.model_alias.slug if prompt.model_alias_id else '',
        'temperature': float(prompt.temperature),
        'max_output_tokens': prompt.max_output_tokens,
        'content_hash': prompt.content_hash,
    }


def _revision_payload(revision: AgentConfigRevision, *, detail: bool = True) -> dict:
    payload = {
        'id': str(revision.id),
        'profile_id': str(revision.profile_id),
        'profile_name': revision.profile.name,
        'profile_scope': revision.profile.scope,
        'version': revision.version,
        'status': revision.status,
        'base_revision_id': str(revision.base_revision_id or ''),
        'context_mode': revision.context_mode,
        'knowledge_mode': revision.knowledge_mode,
        'config_hash': revision.config_hash,
        'validation_report': revision.validation_report,
        'evaluation_summary': revision.evaluation_summary,
        'change_summary': revision.change_summary,
        'created_by_staff_id': str(revision.created_by_staff_id or ''),
        'approved_by_staff_id': str(revision.approved_by_staff_id or ''),
        'submitted_at': revision.submitted_at,
        'approved_at': revision.approved_at,
        'published_at': revision.published_at,
        'created_at': revision.created_at,
        'updated_at': revision.updated_at,
    }
    if detail:
        payload.update({
            'context_policy': revision.context_policy,
            'prompts': [
                _prompt_payload(item)
                for item in revision.prompts.select_related('model_alias').order_by('task_key')
            ],
            'knowledge_bindings': [{
                'knowledge_base_revision_id': str(item.knowledge_base_revision_id),
                'knowledge_base': item.knowledge_base_revision.knowledge_base.name,
                'retrieval_profile_revision_id': str(item.retrieval_profile_revision_id or ''),
                'order': item.order,
            } for item in revision.knowledge_bindings.select_related(
                'knowledge_base_revision__knowledge_base',
                'retrieval_profile_revision',
            )],
        })
    return payload


def _profile_payload(profile: AgentConfigProfile) -> dict:
    return {
        'id': str(profile.id),
        'name': profile.name,
        'description': profile.description,
        'scope': profile.scope,
        'active_revision_id': str(profile.active_revision_id or ''),
        'active_version': profile.active_revision.version if profile.active_revision_id else None,
        'revision_count': profile.revisions.count(),
        'templates': list(profile.interview_templates.values('id', 'name')),
        'updated_at': profile.updated_at,
    }


def _clone_revision(profile: AgentConfigProfile, source, actor, change_summary: str = ''):
    next_version = (
        profile.revisions.aggregate(value=Max('version'))['value'] or 0
    ) + 1
    revision = AgentConfigRevision.objects.create(
        profile=profile,
        base_revision=source,
        version=next_version,
        status=AgentConfigRevision.Status.DRAFT,
        context_mode=source.context_mode if source else (
            AgentConfigRevision.ComponentMode.REPLACE
            if profile.scope == AgentConfigProfile.Scope.PLATFORM
            else AgentConfigRevision.ComponentMode.INHERIT
        ),
        context_policy=deepcopy(source.context_policy) if source else {},
        knowledge_mode=source.knowledge_mode if source else AgentConfigRevision.ComponentMode.INHERIT,
        change_summary=change_summary,
        created_by_staff=actor,
    )
    if source:
        AgentPromptTemplate.objects.bulk_create([
            AgentPromptTemplate(
                revision=revision,
                task_key=item.task_key,
                system_template=item.system_template,
                user_template=item.user_template,
                variable_schema=deepcopy(item.variable_schema),
                output_contract=deepcopy(item.output_contract),
                model_alias=item.model_alias,
                temperature=item.temperature,
                max_output_tokens=item.max_output_tokens,
                content_hash=item.content_hash,
            )
            for item in source.prompts.all()
        ])
        AgentConfigKnowledgeBinding.objects.bulk_create([
            AgentConfigKnowledgeBinding(
                revision=revision,
                knowledge_base_revision=item.knowledge_base_revision,
                retrieval_profile_revision=item.retrieval_profile_revision,
                order=item.order,
            )
            for item in source.knowledge_bindings.all()
        ])
    return revision


class AgentConfigProfileView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def get(self, request):
        rows = AgentConfigProfile.objects.select_related('active_revision').prefetch_related(
            'revisions', 'interview_templates',
        )
        return Response([_profile_payload(item) for item in rows])

    def post(self, request):
        if not _has_permission(request, 'agent_config.manage'):
            return _forbidden('agent_config.manage')
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                scope = request.data.get('scope') or AgentConfigProfile.Scope.TEMPLATE
                if scope not in AgentConfigProfile.Scope.values:
                    return Response({'code': 'agent_config_scope_invalid'}, status=400)
                if (
                    scope == AgentConfigProfile.Scope.PLATFORM
                    and AgentConfigProfile.objects.filter(scope=AgentConfigProfile.Scope.PLATFORM).exists()
                ):
                    return Response({'code': 'platform_profile_already_exists'}, status=409)
                name = str(request.data.get('name') or '').strip()
                if not name:
                    return Response({'code': 'agent_config_profile_name_required'}, status=400)
                profile = AgentConfigProfile.objects.create(
                    name=name,
                    description=request.data.get('description') or '',
                    scope=scope,
                    created_by_staff=request.user,
                )
                source = None
                source_id = request.data.get('clone_revision_id')
                if source_id:
                    source = AgentConfigRevision.objects.filter(pk=source_id).first()
                revision = _clone_revision(
                    profile,
                    source,
                    request.user,
                    request.data.get('change_summary') or reason,
                )
                audit(
                    request,
                    action='agent_config.profile.create',
                    resource_type='AgentConfigProfile',
                    resource_id=profile.id,
                    reason=reason,
                    after={'profile': _profile_payload(profile), 'revision_id': str(revision.id)},
                )
                return Response({
                    'profile': _profile_payload(profile),
                    'revision': _revision_payload(revision),
                }, status=201)

        return run_staff_idempotent(request, 'agent-config:profile:create', execute)


class AgentConfigProfileRevisionView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def get(self, request, profile_id):
        profile = AgentConfigProfile.objects.filter(pk=profile_id).first()
        if not profile:
            return Response({'code': 'profile_not_found'}, status=404)
        return Response([
            _revision_payload(item, detail=False)
            for item in profile.revisions.select_related('profile').all()
        ])

    def post(self, request, profile_id):
        if not _has_permission(request, 'agent_config.manage'):
            return _forbidden('agent_config.manage')
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                profile = AgentConfigProfile.objects.select_for_update().filter(pk=profile_id).first()
                if not profile:
                    return Response({'code': 'profile_not_found'}, status=404)
                source = AgentConfigRevision.objects.filter(
                    pk=request.data.get('source_revision_id') or profile.active_revision_id,
                    profile=profile,
                ).first()
                revision = _clone_revision(
                    profile,
                    source,
                    request.user,
                    request.data.get('change_summary') or reason,
                )
                audit(
                    request,
                    action='agent_config.revision.clone',
                    resource_type='AgentConfigRevision',
                    resource_id=revision.id,
                    reason=reason,
                    before={'source_revision_id': str(source.id) if source else ''},
                    after={'config_hash': revision.config_hash, 'version': revision.version},
                )
                return Response(_revision_payload(revision), status=201)

        return run_staff_idempotent(
            request,
            f'agent-config:profile:{profile_id}:revision:create',
            execute,
        )


class AgentConfigRevisionView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def get(self, request, revision_id):
        revision = AgentConfigRevision.objects.select_related('profile').filter(pk=revision_id).first()
        if not revision:
            return Response({'code': 'revision_not_found'}, status=404)
        return Response(_revision_payload(revision))

    def patch(self, request, revision_id):
        if not _has_permission(request, 'agent_config.manage'):
            return _forbidden('agent_config.manage')
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                revision = AgentConfigRevision.objects.select_for_update().select_related('profile').filter(
                    pk=revision_id,
                ).first()
                if not revision:
                    return Response({'code': 'revision_not_found'}, status=404)
                if revision.status != AgentConfigRevision.Status.DRAFT:
                    return Response({
                        'code': 'published_revision_immutable',
                        'message': '仅草稿可编辑；请克隆新草稿。',
                    }, status=409)
                before = {
                    'config_hash': revision.config_hash,
                    'context_policy': revision.context_policy,
                    'prompt_hashes': list(revision.prompts.values_list('content_hash', flat=True)),
                }
                for field in ('context_mode', 'context_policy', 'knowledge_mode', 'change_summary'):
                    if field in request.data:
                        setattr(revision, field, request.data[field])
                revision.validation_report = {}
                revision.evaluation_summary = {}
                revision.save()
                if 'prompts' in request.data:
                    supplied_keys = set()
                    for data in request.data.get('prompts') or []:
                        task_key = str(data.get('task_key') or '').strip()
                        supplied_keys.add(task_key)
                        alias = None
                        alias_id = data.get('model_alias_id')
                        if alias_id:
                            alias = ModelAlias.objects.filter(pk=alias_id).first()
                            if not alias:
                                return Response({'code': 'model_alias_not_found'}, status=400)
                        prompt, _ = AgentPromptTemplate.objects.update_or_create(
                            revision=revision,
                            task_key=task_key,
                            defaults={
                                'system_template': data.get('system_template') or '',
                                'user_template': data.get('user_template') or '',
                                'variable_schema': data.get('variable_schema') or {},
                                'output_contract': data.get('output_contract') or {},
                                'model_alias': alias,
                                'temperature': data.get('temperature', 0.3),
                                'max_output_tokens': data.get('max_output_tokens') or 800,
                            },
                        )
                        prompt.content_hash = stable_hash({
                            'system_template': prompt.system_template,
                            'user_template': prompt.user_template,
                            'variable_schema': prompt.variable_schema,
                            'output_contract': prompt.output_contract,
                            'model_alias_id': prompt.model_alias_id,
                            'temperature': str(prompt.temperature),
                            'max_output_tokens': prompt.max_output_tokens,
                        })
                        prompt.save(update_fields=['content_hash', 'updated_at'])
                    revision.prompts.exclude(task_key__in=supplied_keys).delete()
                if 'knowledge_bindings' in request.data:
                    revision.knowledge_bindings.all().delete()
                    for index, data in enumerate(request.data.get('knowledge_bindings') or []):
                        kb_revision = KnowledgeBaseRevision.objects.filter(
                            pk=data.get('knowledge_base_revision_id'),
                            status=KnowledgeBaseRevision.Status.PUBLISHED,
                        ).first()
                        if not kb_revision:
                            return Response({'code': 'knowledge_base_revision_not_published'}, status=400)
                        retrieval_revision = None
                        if data.get('retrieval_profile_revision_id'):
                            retrieval_revision = RetrievalProfileRevision.objects.filter(
                                pk=data['retrieval_profile_revision_id'],
                                status=RetrievalProfileRevision.Status.PUBLISHED,
                            ).first()
                            if not retrieval_revision:
                                return Response({'code': 'retrieval_profile_revision_not_published'}, status=400)
                        AgentConfigKnowledgeBinding.objects.create(
                            revision=revision,
                            knowledge_base_revision=kb_revision,
                            retrieval_profile_revision=retrieval_revision,
                            order=int(data.get('order', index)),
                        )
                revision.config_hash = build_revision_hash(revision)
                revision.save(update_fields=['config_hash', 'updated_at'])
                audit(
                    request,
                    action='agent_config.revision.update',
                    resource_type='AgentConfigRevision',
                    resource_id=revision.id,
                    reason=reason,
                    before=before,
                    after={
                        'config_hash': revision.config_hash,
                        'context_policy': revision.context_policy,
                        'prompt_hashes': list(revision.prompts.values_list('content_hash', flat=True)),
                    },
                )
                return Response(_revision_payload(revision))

        return run_staff_idempotent(
            request,
            f'agent-config:revision:{revision_id}:update',
            execute,
        )


class AgentConfigRevisionActionView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def post(self, request, revision_id, action):
        permission = (
            'agent_config.evaluate'
            if action == 'evaluate'
            else 'agent_config.publish'
            if action in {'approve', 'publish', 'rollback'}
            else 'agent_config.manage'
        )
        if not _has_permission(request, permission):
            return _forbidden(permission)
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                revision = AgentConfigRevision.objects.select_for_update().select_related('profile').filter(
                    pk=revision_id,
                ).first()
                if not revision:
                    return Response({'code': 'revision_not_found'}, status=404)
                before = _revision_payload(revision, detail=False)
                now = timezone.now()
                if action == 'validate':
                    if revision.status != AgentConfigRevision.Status.DRAFT:
                        return Response({'code': 'revision_not_draft'}, status=409)
                    revision.config_hash = build_revision_hash(revision)
                    revision.validation_report = validate_agent_config_revision(revision)
                    revision.save(update_fields=['config_hash', 'validation_report'])
                elif action == 'evaluate':
                    if revision.status != AgentConfigRevision.Status.DRAFT:
                        return Response({'code': 'revision_not_draft'}, status=409)
                    revision.config_hash = build_revision_hash(revision)
                    validation = validate_agent_config_revision(revision)
                    if not validation['valid']:
                        return Response({
                            'code': 'revision_validation_failed',
                            'validation_report': validation,
                        }, status=409)
                    dataset = EvaluationDataset.objects.filter(pk=request.data.get('dataset_id')).first()
                    baseline = revision.profile.active_revision
                    retrieval_metrics, result_samples = _evaluate_retrieval_dataset(revision, dataset)
                    baseline_metrics = {}
                    metric_deltas = {}
                    if baseline and baseline.id != revision.id and dataset:
                        baseline_metrics, _ = _evaluate_retrieval_dataset(baseline, dataset)
                        for metric_name, candidate_value in retrieval_metrics.items():
                            baseline_value = baseline_metrics.get(metric_name)
                            if isinstance(candidate_value, (int, float)) and isinstance(baseline_value, (int, float)):
                                metric_deltas[metric_name] = candidate_value - baseline_value
                    metrics = {
                        'hard_gate_pass_rate': 1.0,
                        'prompt_contract_success_rate': None,
                        **retrieval_metrics,
                        'follow_up_relevance': None,
                        'output_contract_success_rate': None,
                        'quality_gate_blocking': False,
                        'candidate_hash': revision.config_hash,
                        'baseline_hash': baseline.config_hash if baseline else '',
                        'baseline': baseline_metrics,
                        'delta': metric_deltas,
                    }
                    run_status = (
                        AgentConfigEvaluationRun.Status.FAILED
                        if metrics['retrieval_case_count']
                        and metrics['retrieval_error_count'] >= metrics['retrieval_case_count']
                        else AgentConfigEvaluationRun.Status.SUCCEEDED
                    )
                    run = AgentConfigEvaluationRun.objects.create(
                        revision=revision,
                        baseline_revision=baseline,
                        dataset=dataset,
                        evaluation_type=request.data.get('evaluation_type') or 'full',
                        status=run_status,
                        metrics=metrics,
                        result_samples=result_samples,
                        error_message=(
                            '全部 retrieval case 执行失败。'
                            if run_status == AgentConfigEvaluationRun.Status.FAILED
                            else ''
                        ),
                        revision_hash=revision.config_hash,
                        created_by_staff=request.user,
                        started_at=now,
                        finished_at=timezone.now(),
                    )
                    summary = {
                        'latest_run_id': str(run.id),
                        'status': run.status,
                        'finished_at': run.finished_at.isoformat(),
                        'metrics': metrics,
                    }
                    AgentConfigRevision.objects.filter(pk=revision.pk).update(
                        config_hash=revision.config_hash,
                        validation_report=validation,
                        evaluation_summary=summary,
                    )
                    revision.refresh_from_db()
                elif action == 'submit':
                    if revision.status != AgentConfigRevision.Status.DRAFT:
                        return Response({'code': 'revision_not_draft'}, status=409)
                    current_hash = build_revision_hash(revision)
                    validation = validate_agent_config_revision(revision)
                    successful_run = revision.config_evaluation_runs.filter(
                        status=AgentConfigEvaluationRun.Status.SUCCEEDED,
                        revision_hash=current_hash,
                        finished_at__gt=revision.updated_at,
                    ).exists()
                    if not validation['valid'] or not successful_run:
                        return Response({
                            'code': 'release_gate_failed',
                            'validation_report': validation,
                            'fresh_evaluation_required': not successful_run,
                        }, status=409)
                    revision.config_hash = current_hash
                    revision.validation_report = validation
                    revision.status = AgentConfigRevision.Status.PENDING_REVIEW
                    revision.submitted_at = now
                    revision.save(update_fields=[
                        'config_hash', 'validation_report', 'status', 'submitted_at',
                    ])
                elif action == 'approve':
                    if revision.status != AgentConfigRevision.Status.PENDING_REVIEW:
                        return Response({'code': 'revision_not_reviewable'}, status=409)
                    revision.status = AgentConfigRevision.Status.APPROVED
                    revision.approved_by_staff = request.user
                    revision.approved_at = now
                    revision.save(update_fields=['status', 'approved_by_staff', 'approved_at'])
                elif action == 'publish':
                    if revision.status != AgentConfigRevision.Status.APPROVED:
                        return Response({'code': 'revision_not_approved'}, status=409)
                    profile = AgentConfigProfile.objects.select_for_update().get(pk=revision.profile_id)
                    previous = profile.active_revision
                    if previous and previous.id != revision.id:
                        previous.status = AgentConfigRevision.Status.SUPERSEDED
                        previous.save(update_fields=['status'])
                    revision.status = AgentConfigRevision.Status.PUBLISHED
                    revision.published_at = now
                    revision.save(update_fields=['status', 'published_at'])
                    profile.active_revision = revision
                    profile.save(update_fields=['active_revision', 'updated_at'])
                elif action == 'rollback':
                    if revision.status not in {
                        AgentConfigRevision.Status.PUBLISHED,
                        AgentConfigRevision.Status.SUPERSEDED,
                    }:
                        return Response({'code': 'revision_not_rollback_target'}, status=409)
                    profile = AgentConfigProfile.objects.select_for_update().get(pk=revision.profile_id)
                    previous = profile.active_revision
                    if previous and previous.id != revision.id:
                        previous.status = AgentConfigRevision.Status.SUPERSEDED
                        previous.save(update_fields=['status'])
                    revision.status = AgentConfigRevision.Status.PUBLISHED
                    revision.save(update_fields=['status'])
                    profile.active_revision = revision
                    profile.save(update_fields=['active_revision', 'updated_at'])
                else:
                    return Response({'code': 'revision_action_invalid'}, status=400)
                after = _revision_payload(revision, detail=False)
                audit(
                    request,
                    action=f'agent_config.revision.{action}',
                    resource_type='AgentConfigRevision',
                    resource_id=revision.id,
                    reason=reason,
                    before=before,
                    after=after,
                    metadata={
                        'self_review': (
                            action in {'approve', 'publish'}
                            and revision.created_by_staff_id == request.user.id
                        ),
                        'config_hash': revision.config_hash,
                    },
                )
                response = {'revision': _revision_payload(revision)}
                if action == 'evaluate':
                    response['evaluation_run'] = {
                        'id': str(run.id),
                        'status': run.status,
                        'metrics': run.metrics,
                    }
                return Response(response)

        return run_staff_idempotent(
            request,
            f'agent-config:revision:{revision_id}:{action}',
            execute,
        )


class AgentConfigResolvedPreviewView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def get(self, request, revision_id):
        revision = AgentConfigRevision.objects.select_related('profile').filter(pk=revision_id).first()
        if not revision:
            return Response({'code': 'revision_not_found'}, status=404)
        try:
            snapshot = resolve_agent_config_revision(revision)
        except AgentConfigurationError as exc:
            return Response({'code': 'preview_unavailable', 'message': str(exc)}, status=409)
        return Response({
            'snapshot': snapshot,
            'context_preview': {
                'section_limits': snapshot['context_policy'].get('section_limits', {}),
                'section_minimums': snapshot['context_policy'].get('section_minimums', {}),
                'drop_order': snapshot['context_policy'].get('drop_order', []),
                'routed_min_context_window': snapshot.get('model_context_window'),
            },
        })


class AgentPromptPreviewView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def post(self, request, task_key):
        revision = AgentConfigRevision.objects.filter(pk=request.data.get('revision_id')).first()
        if not revision:
            return Response({'code': 'revision_not_found'}, status=404)
        prompt = revision.prompts.filter(task_key=task_key).first()
        if not prompt:
            try:
                resolved = resolve_agent_config_revision(revision)
                config = resolved.get('prompts', {}).get(task_key)
            except AgentConfigurationError:
                config = None
            if not config:
                return Response({'code': 'prompt_not_found'}, status=404)
            system_template = config['system_template']
            user_template = config['user_template']
            schema = config.get('variable_schema') or {}
        else:
            system_template = prompt.system_template
            user_template = prompt.user_template
            schema = prompt.variable_schema
        try:
            system_message, user_message, metadata = render_prompt_source(
                system_template=system_template,
                user_template=user_template,
                variable_schema=schema,
                variables=request.data.get('variables') or {},
            )
        except AgentConfigurationError as exc:
            return Response({'code': 'prompt_preview_failed', 'message': str(exc)}, status=400)
        return Response({
            'task_key': task_key,
            'messages': [
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': user_message},
            ],
            'metadata': metadata,
        })


class AgentConfigExperimentView(StaffProtectedView):
    required_permissions = ['agent_config.evaluate']

    def get(self, request):
        rows = AgentConfigEvaluationRun.objects.select_related(
            'revision__profile', 'baseline_revision', 'dataset',
        ).all()[:200]
        return Response([{
            'id': str(item.id),
            'revision_id': str(item.revision_id),
            'profile': item.revision.profile.name,
            'baseline_revision_id': str(item.baseline_revision_id or ''),
            'dataset': item.dataset.name if item.dataset_id else '',
            'evaluation_type': item.evaluation_type,
            'status': item.status,
            'metrics': item.metrics,
            'error_message': item.error_message,
            'created_at': item.created_at,
            'finished_at': item.finished_at,
        } for item in rows])


class AgentConfigEvaluationDatasetView(StaffProtectedView):
    required_permissions = ['agent_config.view']

    def get(self, request):
        return Response([{
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'case_count': item.cases.count(),
            'updated_at': item.updated_at,
        } for item in EvaluationDataset.objects.prefetch_related('cases').all()])


def _retrieval_revision_payload(revision: RetrievalProfileRevision) -> dict:
    return {
        'id': str(revision.id),
        'profile_id': str(revision.profile_id),
        'profile': revision.profile.name,
        'version': revision.version,
        'status': revision.status,
        'config': revision.config,
        'config_hash': revision.config_hash,
        'validation_report': revision.validation_report,
        'evaluation_summary': revision.evaluation_summary,
        'created_at': revision.created_at,
        'updated_at': revision.updated_at,
    }


class RetrievalProfileView(StaffProtectedView):
    required_permissions = ['knowledge_base.manage']

    def get(self, request):
        return Response([{
            'id': str(item.id),
            'name': item.name,
            'description': item.description,
            'active_revision_id': str(item.active_revision_id or ''),
            'active_version': item.active_revision.version if item.active_revision_id else None,
            'revisions': [
                _retrieval_revision_payload(revision)
                for revision in item.revisions.select_related('profile').all()
            ],
        } for item in RetrievalProfile.objects.select_related('active_revision').prefetch_related('revisions')])

    def post(self, request):
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                config = validate_retrieval_config(request.data.get('config') or {})
                profile = RetrievalProfile.objects.create(
                    name=str(request.data.get('name') or '').strip(),
                    description=request.data.get('description') or '',
                    created_by_staff=request.user,
                )
                revision = RetrievalProfileRevision.objects.create(
                    profile=profile,
                    version=1,
                    status=RetrievalProfileRevision.Status.DRAFT,
                    config=config,
                    config_hash=stable_hash(config),
                    validation_report={'valid': True, 'errors': []},
                    change_summary=reason,
                    created_by_staff=request.user,
                )
                audit(
                    request,
                    action='retrieval_profile.create',
                    resource_type='RetrievalProfile',
                    resource_id=profile.id,
                    reason=reason,
                    after={'revision': _retrieval_revision_payload(revision)},
                )
                return Response(_retrieval_revision_payload(revision), status=201)

        return run_staff_idempotent(request, 'retrieval-profile:create', execute)


class RetrievalProfileActionView(StaffProtectedView):
    required_permissions = ['knowledge_base.manage']

    def post(self, request, revision_id, action):
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                revision = RetrievalProfileRevision.objects.select_for_update().select_related('profile').filter(
                    pk=revision_id,
                ).first()
                if not revision:
                    return Response({'code': 'retrieval_revision_not_found'}, status=404)
                before = _retrieval_revision_payload(revision)
                if action == 'clone':
                    if revision.profile.revisions.filter(status=RetrievalProfileRevision.Status.DRAFT).exists():
                        return Response({'code': 'retrieval_draft_already_exists'}, status=409)
                    cloned = RetrievalProfileRevision.objects.create(
                        profile=revision.profile,
                        version=(revision.profile.revisions.aggregate(Max('version'))['version__max'] or 0) + 1,
                        status=RetrievalProfileRevision.Status.DRAFT,
                        config=revision.config,
                        config_hash=revision.config_hash,
                        change_summary=reason,
                        created_by_staff=request.user,
                    )
                    audit(
                        request,
                        action='retrieval_profile.clone',
                        resource_type='RetrievalProfileRevision',
                        resource_id=cloned.id,
                        reason=reason,
                        before=before,
                        after=_retrieval_revision_payload(cloned),
                    )
                    return Response(_retrieval_revision_payload(cloned), status=201)
                if action == 'update':
                    if revision.status != RetrievalProfileRevision.Status.DRAFT:
                        return Response({'code': 'retrieval_revision_immutable'}, status=409)
                    config = validate_retrieval_config(request.data.get('config') or revision.config)
                    revision.config = config
                    revision.config_hash = stable_hash(config)
                    revision.validation_report = {'valid': True, 'errors': []}
                    revision.change_summary = reason
                    revision.save(update_fields=[
                        'config', 'config_hash', 'validation_report', 'change_summary', 'updated_at',
                    ])
                elif action == 'publish':
                    if revision.status != RetrievalProfileRevision.Status.DRAFT:
                        return Response({'code': 'retrieval_revision_immutable'}, status=409)
                    config = validate_retrieval_config(revision.config)
                    previous = revision.profile.active_revision
                    if previous and previous.id != revision.id:
                        previous.status = RetrievalProfileRevision.Status.SUPERSEDED
                        previous.save(update_fields=['status'])
                    revision.config = config
                    revision.config_hash = stable_hash(config)
                    revision.status = RetrievalProfileRevision.Status.PUBLISHED
                    revision.published_at = timezone.now()
                    revision.save(update_fields=[
                        'config', 'config_hash', 'status', 'published_at', 'updated_at',
                    ])
                    revision.profile.active_revision = revision
                    revision.profile.save(update_fields=['active_revision', 'updated_at'])
                else:
                    return Response({'code': 'retrieval_action_invalid'}, status=400)
                audit(
                    request,
                    action=f'retrieval_profile.{action}',
                    resource_type='RetrievalProfileRevision',
                    resource_id=revision.id,
                    reason=reason,
                    before=before,
                    after=_retrieval_revision_payload(revision),
                )
                return Response(_retrieval_revision_payload(revision))

        return run_staff_idempotent(
            request,
            f'retrieval-profile:{revision_id}:{action}',
            execute,
        )


def _knowledge_base_revision_payload(revision: KnowledgeBaseRevision) -> dict:
    return {
        'id': str(revision.id),
        'knowledge_base_id': str(revision.knowledge_base_id),
        'knowledge_base': revision.knowledge_base.name,
        'version': revision.version,
        'status': revision.status,
        'ingestion_policy': revision.ingestion_policy,
        'default_retrieval_revision_id': str(revision.default_retrieval_revision_id or ''),
        'config_hash': revision.config_hash,
        'members': [{
            'document_id': str(member.document_id),
            'title': member.document.title,
            'published_revision_id': str(member.document.published_revision_id or ''),
            'required': member.required,
            'order': member.order,
        } for member in revision.document_bindings.select_related('document')],
        'created_at': revision.created_at,
        'updated_at': revision.updated_at,
    }


class KnowledgeBaseView(StaffProtectedView):
    required_permissions = ['knowledge_base.manage']

    def get(self, request):
        rows = KnowledgeBase.objects.select_related('active_revision').prefetch_related(
            'revisions__document_bindings__document',
        )
        return Response([{
            'id': str(item.id),
            'name': item.name,
            'description': item.description,
            'active_revision_id': str(item.active_revision_id or ''),
            'active_version': item.active_revision.version if item.active_revision_id else None,
            'revisions': [
                _knowledge_base_revision_payload(revision)
                for revision in item.revisions.select_related(
                    'knowledge_base', 'default_retrieval_revision',
                )
            ],
        } for item in rows])

    def post(self, request):
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                policy = validate_ingestion_policy(request.data.get('ingestion_policy') or {})
                retrieval_revision = RetrievalProfileRevision.objects.filter(
                    pk=request.data.get('default_retrieval_revision_id'),
                    status=RetrievalProfileRevision.Status.PUBLISHED,
                ).first()
                if not retrieval_revision:
                    return Response({'code': 'published_retrieval_profile_required'}, status=400)
                kb = KnowledgeBase.objects.create(
                    name=str(request.data.get('name') or '').strip(),
                    description=request.data.get('description') or '',
                    created_by_staff=request.user,
                )
                revision = KnowledgeBaseRevision.objects.create(
                    knowledge_base=kb,
                    version=1,
                    status=KnowledgeBaseRevision.Status.DRAFT,
                    ingestion_policy=policy,
                    default_retrieval_revision=retrieval_revision,
                    config_hash=stable_hash({
                        'ingestion_policy': policy,
                        'retrieval_revision_id': str(retrieval_revision.id),
                        'documents': [],
                    }),
                    change_summary=reason,
                    created_by_staff=request.user,
                )
                audit(
                    request,
                    action='knowledge_base.create',
                    resource_type='KnowledgeBase',
                    resource_id=kb.id,
                    reason=reason,
                    after={'revision': _knowledge_base_revision_payload(revision)},
                )
                return Response(_knowledge_base_revision_payload(revision), status=201)

        return run_staff_idempotent(request, 'knowledge-base:create', execute)


class KnowledgeBaseRevisionView(StaffProtectedView):
    required_permissions = ['knowledge_base.manage']

    def patch(self, request, revision_id):
        reason, error = operation_reason(request)
        if error:
            return error

        def execute():
            with transaction.atomic():
                revision = KnowledgeBaseRevision.objects.select_for_update().select_related(
                    'knowledge_base',
                ).filter(pk=revision_id).first()
                if not revision:
                    return Response({'code': 'knowledge_base_revision_not_found'}, status=404)
                if revision.status != KnowledgeBaseRevision.Status.DRAFT:
                    return Response({'code': 'knowledge_base_revision_immutable'}, status=409)
                before = _knowledge_base_revision_payload(revision)
                if 'ingestion_policy' in request.data:
                    revision.ingestion_policy = validate_ingestion_policy(request.data['ingestion_policy'])
                if request.data.get('default_retrieval_revision_id'):
                    retrieval = RetrievalProfileRevision.objects.filter(
                        pk=request.data['default_retrieval_revision_id'],
                        status=RetrievalProfileRevision.Status.PUBLISHED,
                    ).first()
                    if not retrieval:
                        return Response({'code': 'published_retrieval_profile_required'}, status=400)
                    revision.default_retrieval_revision = retrieval
                revision.save()
                if 'members' in request.data:
                    revision.document_bindings.all().delete()
                    for index, data in enumerate(request.data.get('members') or []):
                        document = KnowledgeDocument.objects.filter(
                            pk=data.get('document_id'),
                            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
                            status=KnowledgeDocument.Status.INDEXED,
                            published_revision__isnull=False,
                        ).first()
                        if not document:
                            return Response({'code': 'published_document_required'}, status=400)
                        KnowledgeBaseRevisionDocument.objects.create(
                            revision=revision,
                            document=document,
                            required=bool(data.get('required')),
                            order=int(data.get('order', index)),
                        )
                revision.config_hash = stable_hash({
                    'ingestion_policy': revision.ingestion_policy,
                    'retrieval_revision_id': str(revision.default_retrieval_revision_id),
                    'documents': list(revision.document_bindings.order_by('order').values(
                        'document_id', 'required', 'order',
                    )),
                })
                revision.save(update_fields=['config_hash', 'updated_at'])
                audit(
                    request,
                    action='knowledge_base.revision.update',
                    resource_type='KnowledgeBaseRevision',
                    resource_id=revision.id,
                    reason=reason,
                    before=before,
                    after=_knowledge_base_revision_payload(revision),
                )
                return Response(_knowledge_base_revision_payload(revision))

        return run_staff_idempotent(
            request,
            f'knowledge-base-revision:{revision_id}:update',
            execute,
        )

    def post(self, request, revision_id):
        reason, error = operation_reason(request)
        if error:
            return error
        action = request.data.get('action')

        def execute():
            with transaction.atomic():
                revision = KnowledgeBaseRevision.objects.select_for_update().select_related(
                    'knowledge_base',
                ).filter(pk=revision_id).first()
                if not revision:
                    return Response({'code': 'knowledge_base_revision_not_found'}, status=404)
                if action == 'clone':
                    if revision.knowledge_base.revisions.filter(status=KnowledgeBaseRevision.Status.DRAFT).exists():
                        return Response({'code': 'knowledge_base_draft_already_exists'}, status=409)
                    cloned = KnowledgeBaseRevision.objects.create(
                        knowledge_base=revision.knowledge_base,
                        version=(
                            revision.knowledge_base.revisions.aggregate(Max('version'))['version__max'] or 0
                        ) + 1,
                        status=KnowledgeBaseRevision.Status.DRAFT,
                        ingestion_policy=revision.ingestion_policy,
                        default_retrieval_revision=revision.default_retrieval_revision,
                        config_hash=revision.config_hash,
                        change_summary=reason,
                        created_by_staff=request.user,
                    )
                    KnowledgeBaseRevisionDocument.objects.bulk_create([
                        KnowledgeBaseRevisionDocument(
                            revision=cloned,
                            document=binding.document,
                            required=binding.required,
                            order=binding.order,
                        )
                        for binding in revision.document_bindings.select_related('document')
                    ])
                    audit(
                        request,
                        action='knowledge_base.revision.clone',
                        resource_type='KnowledgeBaseRevision',
                        resource_id=cloned.id,
                        reason=reason,
                        before=_knowledge_base_revision_payload(revision),
                        after=_knowledge_base_revision_payload(cloned),
                    )
                    return Response(_knowledge_base_revision_payload(cloned), status=201)
                if action != 'publish' or revision.status != KnowledgeBaseRevision.Status.DRAFT:
                    return Response({'code': 'knowledge_base_action_invalid'}, status=409)
                if revision.document_bindings.filter(document__published_revision__isnull=True).exists():
                    return Response({'code': 'knowledge_base_has_unpublished_documents'}, status=409)
                previous = revision.knowledge_base.active_revision
                if previous and previous.id != revision.id:
                    previous.status = KnowledgeBaseRevision.Status.SUPERSEDED
                    previous.save(update_fields=['status'])
                revision.status = KnowledgeBaseRevision.Status.PUBLISHED
                revision.published_at = timezone.now()
                revision.approved_by_staff = request.user
                revision.approved_at = timezone.now()
                revision.save(update_fields=[
                    'status', 'published_at', 'approved_by_staff', 'approved_at', 'updated_at',
                ])
                revision.knowledge_base.active_revision = revision
                revision.knowledge_base.save(update_fields=['active_revision', 'updated_at'])
                audit(
                    request,
                    action='knowledge_base.revision.publish',
                    resource_type='KnowledgeBaseRevision',
                    resource_id=revision.id,
                    reason=reason,
                    after=_knowledge_base_revision_payload(revision),
                )
                return Response(_knowledge_base_revision_payload(revision))

        return run_staff_idempotent(
            request,
            f'knowledge-base-revision:{revision_id}:{action}',
            execute,
        )
