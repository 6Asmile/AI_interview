from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response

from .idempotency import run_staff_idempotent
from .models import BreakGlassGrant, MaintenanceNotice, PlatformFeatureFlag
from .views import StaffProtectedView, audit


def operation_envelope(operation, **compatibility_fields):
    """Return the public Operation identity while preserving legacy fields."""

    payload = {
        'operation_id': str(operation.pk),
        'status': 'accepted',
        'events_url': f'/api/v2/operations/{operation.pk}/events/',
        'result_url': f'/api/v2/operations/{operation.pk}/',
    }
    payload.update(compatibility_fields)
    return payload


def staff_operation_principal(staff_account):
    """Resolve an explicitly linked business principal for global commands.

    Staff accounts intentionally live in a separate authentication domain. We
    only use a same-email, privileged business account as Operation owner and
    never silently borrow an unrelated superuser.
    """

    from users.models import User

    return User.objects.filter(
        email__iexact=staff_account.email,
        role=User.Role.ADMIN,
        is_active=True,
    ).first()


def operation_reason(request, message='该操作必须填写原因。'):
    reason = str(request.data.get('operation_reason') or '').strip()
    return reason, None if reason else Response({'code': 'operation_reason_required', 'message': message}, status=400)


def has_private_grant(request, candidate_id):
    grant_id = request.query_params.get('grant_id') or request.headers.get('X-Break-Glass-Grant')
    if not grant_id:
        return False
    return BreakGlassGrant.objects.filter(
        id=grant_id,
        account=request.user,
        candidate_id=candidate_id,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).exists()


class InterviewSessionAdminListView(StaffProtectedView):
    required_permissions = ['interview.audit']

    def get(self, request):
        from interviews.models import InterviewSession
        rows = InterviewSession.objects.select_related('user', 'template').annotate(
            question_total=Count('questions'), run_total=Count('agent_runs', distinct=True),
        ).order_by('-created_at')
        if request.query_params.get('status'):
            rows = rows.filter(status=request.query_params['status'])
        if request.query_params.get('search'):
            search = request.query_params['search'].strip()
            rows = rows.filter(models.Q(user__email__icontains=search) | models.Q(job_position__icontains=search))
        return Response([{
            'id': str(item.id), 'candidate_id': item.user_id, 'candidate_email': item.user.email,
            'job_position': item.job_position, 'status': item.status, 'current_stage': item.current_stage,
            'interview_mode': item.interview_mode, 'experience_mode': item.experience_mode,
            'question_total': item.question_total, 'run_total': item.run_total,
            'target_duration_minutes': item.target_duration_minutes, 'last_activity_at': item.last_activity_at,
            'created_at': item.created_at, 'finished_at': item.finished_at,
        } for item in rows[:300]])


class ResilienceMetricsAdminView(StaffProtectedView):
    required_permissions = ['tasks.manage']

    def get(self, request):
        from core.models import IdempotencyRecord
        from interviews.models import InterviewAgentDispatch, InterviewAgentExecution, InterviewQuestionGenerationJob

        execution_statuses = dict(
            InterviewAgentExecution.objects.values('status').annotate(total=Count('id')).values_list('status', 'total')
        )
        dispatch_statuses = dict(
            InterviewAgentDispatch.objects.values('status').annotate(total=Count('id')).values_list('status', 'total')
        )
        generation_statuses = dict(
            InterviewQuestionGenerationJob.objects.values('status').annotate(total=Count('id')).values_list('status', 'total')
        )
        idempotency_statuses = dict(
            IdempotencyRecord.objects.values('status').annotate(total=Count('id')).values_list('status', 'total')
        )
        cache_metrics = {}
        try:
            from django_redis import get_redis_connection
            redis = get_redis_connection('default')
            keys = list(redis.scan_iter('ifaceoff:cache-metric:*', count=100))[:200]
            if keys:
                values = redis.mget(keys)
                cache_metrics = {
                    (key.decode() if isinstance(key, bytes) else str(key)).removeprefix('ifaceoff:cache-metric:'):
                    int(value or 0)
                    for key, value in zip(keys, values)
                }
        except Exception:
            cache_metrics = {'redis_metrics_unavailable': 1}
        stale_cutoff = timezone.now() - timedelta(
            seconds=int(getattr(settings, 'AGENT_EXECUTION_STALE_SECONDS', 360))
        )
        return Response({
            'executions': execution_statuses,
            'dispatch_outbox': dispatch_statuses,
            'generation_jobs': generation_statuses,
            'idempotency': idempotency_statuses,
            'stale_execution_count': InterviewAgentExecution.objects.filter(
                status__in=['answer_persisted', 'evaluating', 'evaluated', 'generating'],
                updated_at__lt=stale_cutoff,
            ).count(),
            'cache_metrics': cache_metrics,
            'generated_at': timezone.now(),
        })


class InterviewSessionAdminDetailView(StaffProtectedView):
    required_permissions = ['interview.audit']

    def get(self, request, session_id):
        from interviews.models import InterviewSession
        session = InterviewSession.objects.select_related('user', 'template', 'resume_version', 'job_target').filter(pk=session_id).first()
        if not session:
            return Response({'code': 'interview_not_found', 'message': '面试会话不存在。'}, status=404)
        private = has_private_grant(request, session.user_id)
        questions = [{
            'id': item.id, 'sequence': item.sequence, 'question_text': item.question_text,
            'answer_text': item.answer_text if private else None,
            'answer_protected': bool(item.answer_text and not private),
            'score': item.score, 'target_dimension': item.target_dimension,
            'generation_mode': item.generation_mode, 'validation_status': item.validation_status,
            'question_plan': item.question_plan, 'rag_context': item.rag_context,
            'ai_feedback': item.ai_feedback if private else None,
            'created_at': item.created_at, 'answered_at': item.answered_at,
        } for item in session.questions.order_by('sequence')]
        return Response({
            'id': str(session.id), 'candidate_id': session.user_id, 'candidate_email': session.user.email,
            'job_position': session.job_position, 'status': session.status, 'current_stage': session.current_stage,
            'session_plan': session.session_plan, 'template_snapshot': session.template_snapshot,
            'coverage_summary': session.coverage_summary, 'question_count': session.question_count,
            'target_duration_minutes': session.target_duration_minutes, 'started_at': session.started_at,
            'finished_at': session.finished_at, 'last_activity_at': session.last_activity_at,
            'report_available': bool(session.report), 'private_access': private, 'questions': questions,
        })


class InterviewSessionAdminActionView(StaffProtectedView):
    required_permissions = ['interview.operate']

    def post(self, request, session_id, action):
        from interviews.models import InterviewAgentRun, InterviewSession
        reason, error = operation_reason(request, '面试修复操作必须填写原因。')
        if error:
            return error

        def execute():
            session = InterviewSession.objects.filter(pk=session_id).first()
            if not session:
                return Response({'code': 'interview_not_found', 'message': '面试会话不存在。'}, status=404)
            before = {'status': session.status}
            if action == 'terminate':
                if session.status not in {InterviewSession.Status.PENDING, InterviewSession.Status.RUNNING}:
                    return Response({'code': 'interview_not_running', 'message': '仅能终止未完成面试。'}, status=409)
                session.status = InterviewSession.Status.CANCELED
                session.finished_at = timezone.now()
                session.last_activity_at = timezone.now()
                session.save(update_fields=['status', 'finished_at', 'last_activity_at', 'updated_at'])
                InterviewAgentRun.objects.filter(session=session, status__in=[
                    InterviewAgentRun.Status.PENDING, InterviewAgentRun.Status.RUNNING,
                    InterviewAgentRun.Status.WAITING_GENERATION,
                ]).update(status=InterviewAgentRun.Status.FAILED, fallback_reason='terminated_by_staff', completed_at=timezone.now())
            else:
                return Response({'code': 'interview_action_invalid', 'message': '不支持的面试操作。'}, status=400)
            audit(request, action=f'interview.{action}', resource_type='InterviewSession', resource_id=session.id, reason=reason, before=before, after={'status': session.status})
            return Response({'id': str(session.id), 'status': session.status})

        return run_staff_idempotent(request, f'interview:{session_id}:{action}', execute)


class AgentRunAdminDetailView(StaffProtectedView):
    required_permissions = ['interview.audit']

    def get(self, request, run_id):
        from interviews.models import InterviewAgentRun
        run = InterviewAgentRun.objects.select_related('session__user').filter(pk=run_id).first()
        if not run:
            return Response({'code': 'agent_run_not_found', 'message': 'Agent Run 不存在。'}, status=404)
        return Response({
            'run_id': str(run.id), 'session_id': str(run.session_id), 'candidate_id': run.session.user_id,
            'candidate_email': run.session.user.email, 'event': run.event, 'engine_name': run.engine_name,
            'status': run.status, 'current_node': run.current_node, 'attempt_count': run.attempt_count,
            'fallback_reason': run.fallback_reason, 'error_message': run.error_message,
            'prompt_version': run.prompt_version, 'model_config_snapshot': run.model_config_snapshot,
            'created_at': run.created_at, 'completed_at': run.completed_at,
            'nodes': [{
                'id': item.id, 'node_name': item.node_name, 'subagent_name': item.subagent_name,
                'status': item.status, 'attempt': item.attempt, 'output_summary': item.output_summary,
                'error_message': item.error_message, 'fallback_reason': item.fallback_reason,
                'latency_ms': item.latency_ms, 'token_usage': item.token_usage,
                'started_at': item.started_at, 'completed_at': item.completed_at,
            } for item in run.node_runs.order_by('created_at', 'id')],
            'traces': [{
                'id': item.id, 'event': item.event, 'stage': item.stage, 'subagent_name': item.subagent_name,
                'question_plan': item.question_plan, 'rag_context': item.rag_context,
                'validation_errors': item.validation_errors, 'fallback_reason': item.fallback_reason,
                'context_budget': item.context_budget, 'created_at': item.created_at,
                'tool_calls': [{
                    'id': tool.id, 'node_name': tool.node_name, 'tool_name': tool.tool_name,
                    'subagent_name': tool.subagent_name, 'permission_scope': tool.permission_scope,
                    'status': tool.status, 'output_summary': tool.output_summary,
                    'fallback_reason': tool.fallback_reason, 'latency_ms': tool.latency_ms,
                } for tool in item.tool_calls.order_by('created_at')],
            } for item in run.traces.prefetch_related('tool_calls').order_by('created_at')],
        })


class InterviewConfigAdminView(StaffProtectedView):
    required_permissions = ['template.manage']

    def get(self, request, resource):
        from interviews.models import EvaluationDataset, EvaluationRun, InterviewRubric, InterviewTemplate
        if resource == 'rubrics':
            rows = InterviewRubric.objects.prefetch_related('dimensions__anchors').order_by('-updated_at')
            return Response([{
                'id': item.id, 'name': item.name, 'description': item.description, 'version': item.version,
                'visibility': item.visibility, 'is_active': item.is_active, 'dimension_count': item.dimensions.count(),
                'updated_at': item.updated_at,
            } for item in rows])
        if resource == 'templates':
            rows = InterviewTemplate.objects.select_related('rubric').prefetch_related('stages').order_by('-updated_at')
            return Response([{
                'id': item.id, 'name': item.name, 'description': item.description, 'rubric_id': item.rubric_id,
                'rubric_name': item.rubric.name, 'version': item.version, 'visibility': item.visibility,
                'interview_mode': item.interview_mode, 'target_duration_minutes': item.target_duration_minutes,
                'is_active': item.is_active, 'stage_count': item.stages.count(), 'updated_at': item.updated_at,
            } for item in rows])
        if resource == 'datasets':
            rows = EvaluationDataset.objects.annotate(case_count=Count('cases')).order_by('-updated_at')
            return Response([{'id': item.id, 'name': item.name, 'description': item.description, 'visibility': item.visibility, 'case_count': item.case_count, 'updated_at': item.updated_at} for item in rows])
        if resource == 'runs':
            rows = EvaluationRun.objects.select_related('dataset', 'template').prefetch_related('metrics').order_by('-created_at')
            return Response([{
                'id': item.id, 'dataset': item.dataset.name, 'template': item.template.name if item.template else None,
                'status': item.status, 'summary': item.summary, 'error_message': item.error_message,
                'metric_count': item.metrics.count(), 'created_at': item.created_at, 'finished_at': item.finished_at,
            } for item in rows[:200]])
        return Response({'code': 'config_resource_invalid', 'message': '不支持的配置资源。'}, status=404)

    def post(self, request, resource):
        from interviews.models import EvaluationDataset, EvaluationRun, InterviewRubric, InterviewTemplate
        reason, error = operation_reason(request, '创建面试配置必须填写原因。')
        if error:
            return error

        def execute():
            operation = None
            if resource == 'rubrics':
                item = InterviewRubric.objects.create(
                    name=str(request.data.get('name') or '').strip(), description=request.data.get('description') or '',
                    visibility=request.data.get('visibility') or InterviewRubric.Visibility.SHARED,
                )
            elif resource == 'templates':
                rubric = InterviewRubric.objects.filter(pk=request.data.get('rubric_id')).first()
                if not rubric:
                    return Response({'code': 'rubric_required', 'message': '请选择有效评分量表。'}, status=400)
                item = InterviewTemplate.objects.create(
                    name=str(request.data.get('name') or '').strip(), description=request.data.get('description') or '',
                    rubric=rubric, visibility=request.data.get('visibility') or InterviewTemplate.Visibility.SHARED,
                    interview_mode=request.data.get('interview_mode') or InterviewTemplate.InterviewMode.PROJECT_WITH_FUNDAMENTALS,
                    target_duration_minutes=max(10, int(request.data.get('target_duration_minutes') or 30)),
                )
            elif resource == 'datasets':
                item = EvaluationDataset.objects.create(
                    name=str(request.data.get('name') or '').strip(), description=request.data.get('description') or '',
                    visibility=request.data.get('visibility') or EvaluationDataset.Visibility.SHARED,
                )
            elif resource == 'runs':
                dataset = EvaluationDataset.objects.filter(pk=request.data.get('dataset_id')).first()
                if not dataset:
                    return Response({'code': 'dataset_required', 'message': '请选择有效评估数据集。'}, status=400)
                principal = staff_operation_principal(request.user)
                if not principal:
                    return Response({
                        'code': 'staff_operation_principal_missing',
                        'message': '当前员工账号未绑定同邮箱的平台管理员业务账号，无法创建离线评估 Operation。',
                    }, status=409)
                import hashlib
                import json
                from core.operations import create_operation_with_dispatch

                with transaction.atomic():
                    item = EvaluationRun.objects.create(
                        dataset=dataset,
                        template_id=request.data.get('template_id') or None,
                        config_snapshot={'triggered_by_staff': str(request.user.id)},
                        created_by=principal,
                    )
                    snapshot = {
                        'evaluation_run_id': item.id,
                        'dataset_id': item.dataset_id,
                        'template_id': item.template_id,
                        'config_snapshot': item.config_snapshot,
                    }
                    input_hash = hashlib.sha256(json.dumps(
                        snapshot,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(',', ':'),
                        default=str,
                    ).encode('utf-8')).hexdigest()
                    operation = create_operation_with_dispatch(
                        user=principal,
                        operation_type='interview.evaluation',
                        source_app='interviews',
                        source_model='EvaluationRun',
                        source_id=str(item.id),
                        title=f'离线评估：{dataset.name}',
                        input_type='EvaluationRun',
                        input_id=str(item.id),
                        input_version='1',
                        input_hash=input_hash,
                        metadata={
                            'evaluation_run_id': item.id,
                            'dataset_id': item.dataset_id,
                            'triggered_by_staff_id': str(request.user.id),
                            'operation_reason': reason,
                        },
                        max_attempts=3,
                        queue=getattr(settings, 'CELERY_CAREER_QUEUE', 'ifaceoff.v2.career.analysis'),
                        routing_key='career.analysis',
                    )
                    item.operation = operation
                    item.save(update_fields=['operation'])
            else:
                return Response({'code': 'config_resource_invalid', 'message': '不支持的配置资源。'}, status=404)
            audit(request, action=f'interview_config.{resource}.create', resource_type=item.__class__.__name__, resource_id=item.pk, reason=reason, after={'name': getattr(item, 'name', str(item))})
            if operation:
                return Response(operation_envelope(
                    operation,
                    id=item.pk,
                    created=True,
                ), status=202)
            return Response({'id': item.pk, 'created': True}, status=201)

        return run_staff_idempotent(request, f'interview_config_create:{resource}', execute)


class KnowledgeReviewAdminDetailView(StaffProtectedView):
    required_permissions = ['knowledge.review']

    def get(self, request, document_id):
        from knowledge.models import KnowledgeDocument
        document = KnowledgeDocument.objects.select_related('created_by', 'draft_revision', 'published_revision').filter(pk=document_id).first()
        if not document:
            return Response({'code': 'knowledge_not_found', 'message': '知识文档不存在。'}, status=404)
        revision = document.draft_revision
        return Response({
            'id': str(document.id), 'title': document.title, 'visibility': document.visibility,
            'source_type': document.source_type, 'file_type': document.file_type,
            'parse_status': document.parse_status, 'parser_name': document.parser_name,
            'parser_version': document.parser_version, 'parser_fallback_reason': document.parser_fallback_reason,
            'approval_status': document.approval_status, 'index_status': document.status,
            'owner': document.created_by.email if document.created_by else None,
            'job_positions': document.job_positions, 'ability_tags': document.ability_tags,
            'difficulty': document.difficulty, 'retrieval_count': document.retrieval_count,
            'draft_revision': ({
                'id': str(revision.id), 'version_number': revision.version_number, 'status': revision.status,
                'source_content': revision.source_content, 'parser_snapshot': revision.parser_snapshot,
                'chunks': [{
                    'id': str(chunk.id), 'order': chunk.order, 'block_type': chunk.block_type,
                    'heading_path': chunk.heading_path, 'page_start': chunk.page_start, 'page_end': chunk.page_end,
                    'content': chunk.content, 'table_data': chunk.table_data, 'metadata': chunk.metadata,
                    'token_count': chunk.token_count, 'is_excluded': chunk.is_excluded,
                } for chunk in revision.chunk_drafts.order_by('order')],
            } if revision else None),
            'published_revision_id': str(document.published_revision_id) if document.published_revision_id else None,
        })


def normalize_chunk_orders(revision):
    chunks = list(revision.chunk_drafts.order_by('order', 'created_at'))
    revision.chunk_drafts.update(order=models.F('order') + 100000)
    for index, chunk in enumerate(chunks, start=1):
        chunk.order = index
        chunk.save(update_fields=['order'])


class KnowledgeChunkDraftAdminView(StaffProtectedView):
    required_permissions = ['knowledge.operate']

    def patch(self, request, chunk_id):
        from knowledge.models import KnowledgeChunkDraft, KnowledgeDocumentRevision
        reason, error = operation_reason(request, '编辑知识块必须填写原因。')
        if error:
            return error

        def execute():
            chunk = KnowledgeChunkDraft.objects.select_related('revision__document').filter(pk=chunk_id).first()
            if not chunk:
                return Response({'code': 'chunk_draft_not_found', 'message': '知识块草稿不存在。'}, status=404)
            if chunk.revision.status not in {KnowledgeDocumentRevision.Status.DRAFT, KnowledgeDocumentRevision.Status.PENDING_REVIEW}:
                return Response({'code': 'revision_frozen', 'message': '已发布版本不可直接编辑。'}, status=409)
            before = {'content': chunk.content[:300], 'is_excluded': chunk.is_excluded, 'order': chunk.order}
            for field in ['content', 'block_type', 'heading_path', 'table_data', 'metadata', 'is_excluded']:
                if field in request.data:
                    setattr(chunk, field, request.data[field])
            chunk.token_count = max(1, len(chunk.content) // 2)
            chunk.save()
            audit(request, action='knowledge.chunk.update', resource_type='KnowledgeChunkDraft', resource_id=chunk.id, reason=reason, before=before, after={'content': chunk.content[:300], 'is_excluded': chunk.is_excluded, 'order': chunk.order})
            return Response({'id': str(chunk.id), 'content': chunk.content, 'token_count': chunk.token_count, 'is_excluded': chunk.is_excluded})

        return run_staff_idempotent(request, f'knowledge_chunk_update:{chunk_id}', execute)


class KnowledgeChunkDraftActionView(StaffProtectedView):
    required_permissions = ['knowledge.operate']

    def post(self, request, chunk_id, action):
        from knowledge.models import KnowledgeChunkDraft, KnowledgeDocumentRevision
        reason, error = operation_reason(request, '知识块结构操作必须填写原因。')
        if error:
            return error

        def execute():
            with transaction.atomic():
                chunk = KnowledgeChunkDraft.objects.select_for_update().select_related('revision__document').filter(pk=chunk_id).first()
                if not chunk:
                    return Response({'code': 'chunk_draft_not_found', 'message': '知识块草稿不存在。'}, status=404)
                if chunk.revision.status not in {KnowledgeDocumentRevision.Status.DRAFT, KnowledgeDocumentRevision.Status.PENDING_REVIEW}:
                    return Response({'code': 'revision_frozen', 'message': '已发布版本不可直接编辑。'}, status=409)
                if action == 'split':
                    position = int(request.data.get('position') or 0)
                    if position <= 0 or position >= len(chunk.content):
                        return Response({'code': 'split_position_invalid', 'message': '拆分位置无效。'}, status=400)
                    first, second = chunk.content[:position].strip(), chunk.content[position:].strip()
                    chunk.content = first
                    chunk.token_count = max(1, len(first) // 2)
                    chunk.save(update_fields=['content', 'token_count', 'updated_at'])
                    revision = chunk.revision
                    revision.chunk_drafts.filter(order__gt=chunk.order).update(order=models.F('order') + 100000)
                    KnowledgeChunkDraft.objects.create(
                        revision=revision, order=chunk.order + 1, block_type=chunk.block_type,
                        heading_path=chunk.heading_path, page_start=chunk.page_start, page_end=chunk.page_end,
                        content=second, table_data=chunk.table_data, metadata=chunk.metadata,
                        token_count=max(1, len(second) // 2),
                    )
                    normalize_chunk_orders(revision)
                elif action == 'merge-next':
                    next_chunk = chunk.revision.chunk_drafts.filter(order__gt=chunk.order).order_by('order').first()
                    if not next_chunk:
                        return Response({'code': 'next_chunk_missing', 'message': '没有可合并的下一个知识块。'}, status=409)
                    chunk.content = f'{chunk.content.rstrip()}\n\n{next_chunk.content.lstrip()}'
                    chunk.token_count = max(1, len(chunk.content) // 2)
                    chunk.save(update_fields=['content', 'token_count', 'updated_at'])
                    next_chunk.delete()
                    normalize_chunk_orders(chunk.revision)
                else:
                    return Response({'code': 'chunk_action_invalid', 'message': '不支持的知识块操作。'}, status=400)
                audit(request, action=f'knowledge.chunk.{action}', resource_type='KnowledgeChunkDraft', resource_id=chunk.id, reason=reason, after={'revision_id': str(chunk.revision_id)})
                return Response({'revision_id': str(chunk.revision_id), 'changed': True})

        return run_staff_idempotent(request, f'knowledge_chunk:{chunk_id}:{action}', execute)


class KnowledgeDocumentAdminActionView(StaffProtectedView):
    required_permissions = ['knowledge.operate']

    def post(self, request, document_id, action):
        from knowledge.models import KnowledgeDocument
        from knowledge.operation_handlers import (
            REINDEX_OPERATION,
            REPARSE_OPERATION,
            create_knowledge_operation,
        )
        reason, error = operation_reason(request, '知识文档操作必须填写原因。')
        if error:
            return error

        def execute():
            operation = None
            with transaction.atomic():
                # Lock only the document row; created_by is nullable and must
                # not be pulled into a PostgreSQL FOR UPDATE outer join.
                document = KnowledgeDocument.objects.select_for_update().filter(
                    pk=document_id,
                ).first()
                if not document:
                    return Response({'code': 'knowledge_not_found', 'message': '知识文档不存在。'}, status=404)
                if action in {'reparse', 'reindex'} and not document.created_by:
                    return Response({
                        'code': 'knowledge_operation_owner_missing',
                        'message': '该知识文档缺少可审计的业务所有者，无法创建异步 Operation。',
                    }, status=409)
                if action == 'reparse':
                    document.parse_status = KnowledgeDocument.ParseStatus.PENDING
                    document.parser_fallback_reason = ''
                    document.save(update_fields=['parse_status', 'parser_fallback_reason', 'updated_at'])
                    operation = create_knowledge_operation(
                        user=document.created_by,
                        operation_type=REPARSE_OPERATION,
                        source_model='KnowledgeDocument',
                        source_id=document.id,
                        title=f'重新解析知识文档：{document.title}',
                        metadata={
                            'triggered_by_staff_id': str(request.user.id),
                            'operation_reason': reason,
                        },
                    )
                elif action == 'reindex':
                    if document.approval_status != KnowledgeDocument.ApprovalStatus.APPROVED or not document.published_revision_id:
                        return Response({'code': 'knowledge_not_published', 'message': '仅能重建已审批发布版本的索引。'}, status=409)
                    document.status = KnowledgeDocument.Status.INDEXING
                    document.save(update_fields=['status', 'updated_at'])
                    operation = create_knowledge_operation(
                        user=document.created_by,
                        operation_type=REINDEX_OPERATION,
                        source_model='KnowledgeDocument',
                        source_id=document.id,
                        input_version=str(document.published_revision_id),
                        title=f'重建知识文档索引：{document.title}',
                        metadata={
                            'triggered_by_staff_id': str(request.user.id),
                            'operation_reason': reason,
                        },
                    )
                elif action == 'archive':
                    document.approval_status = KnowledgeDocument.ApprovalStatus.ARCHIVED
                    document.save(update_fields=['approval_status', 'updated_at'])
                else:
                    return Response({'code': 'knowledge_action_invalid', 'message': '不支持的知识文档操作。'}, status=400)
            audit(request, action=f'knowledge.{action}', resource_type='KnowledgeDocument', resource_id=document.id, reason=reason, after={'approval_status': document.approval_status, 'index_status': document.status})
            response = {
                'id': str(document.id),
                'approval_status': document.approval_status,
                'index_status': document.status,
            }
            if operation:
                response.update(operation_envelope(operation))
                return Response(response, status=202)
            return Response(response)

        return run_staff_idempotent(request, f'knowledge_document:{document_id}:{action}', execute)


class AdminTaskActionView(StaffProtectedView):
    required_permissions = ['tasks.manage']

    def post(self, request, operation_id, action):
        from core.models import AsyncOperation
        from core.operations import (
            OperationConflict,
            request_operation_cancel,
            request_operation_retry,
        )
        reason, error = operation_reason(request, '任务操作必须填写原因。')
        if error:
            return error

        def execute():
            operation = AsyncOperation.objects.select_related('user').filter(pk=operation_id).first()
            if not operation:
                return Response({'code': 'task_not_found', 'message': '任务不存在。'}, status=404)
            before = {'status': operation.status, 'error_code': operation.error_code}
            if action == 'retry':
                from core.task_registry import (
                    can_retry_legacy_source,
                    retry_legacy_operation_source,
                )

                uses_generic_dispatch = operation.dispatches.exists()
                is_agent_dispatch = operation.operation_type == 'interview.agent_turn'
                try:
                    if uses_generic_dispatch:
                        operation = request_operation_retry(operation.pk)
                    elif is_agent_dispatch:
                        operation = request_operation_retry(
                            operation.pk,
                            dispatch_retry=False,
                        )
                        operation = retry_legacy_operation_source(operation)
                    elif can_retry_legacy_source(operation):
                        forwarded = retry_legacy_operation_source(operation)
                        operation = forwarded[0] if isinstance(forwarded, list) else forwarded
                    else:
                        raise OperationConflict('operation_not_retryable')
                except (OperationConflict, ValueError) as exc:
                    return Response({'code': 'task_retry_unsupported', 'message': str(exc)}, status=409)
            elif action == 'cancel':
                operation = request_operation_cancel(operation.pk)
            else:
                return Response({'code': 'task_action_invalid', 'message': '不支持的任务操作。'}, status=400)
            audit(request, action=f'task.{action}', resource_type='AsyncOperation', resource_id=operation.id, reason=reason, before=before, after={'status': operation.status})
            return Response(operation_envelope(
                operation,
                id=str(operation.id),
                status=operation.status,
            ))

        return run_staff_idempotent(request, f'task:{operation_id}:{action}', execute)


class GatewayResourceAdminView(StaffProtectedView):
    required_permissions = ['gateway.manage']

    def get(self, request, resource):
        from system.models import ModelAlias, ModelDeployment, ModelRequestLedger, ProviderCredential, RoutePolicy, UsageBudget
        if resource == 'credentials':
            return Response([{'id': item.id, 'name': item.name, 'provider': item.provider, 'scope': item.scope, 'secret_hint': item.secret_hint, 'is_active': item.is_active, 'last_verified_at': item.last_verified_at, 'updated_at': item.updated_at} for item in ProviderCredential.objects.filter(scope=ProviderCredential.Scope.PLATFORM)])
        if resource == 'deployments':
            return Response([{'id': item.id, 'name': item.name, 'provider': item.provider, 'remote_model': item.remote_model, 'model_type': item.model_type, 'base_url': item.base_url, 'credential_id': item.credential_id, 'context_window': item.context_window, 'tokenizer_family': item.tokenizer_family, 'tokenizer_name': item.tokenizer_name, 'priority': item.priority, 'timeout_seconds': item.timeout_seconds, 'is_active': item.is_active, 'last_health_status': item.last_health_status, 'last_health_at': item.last_health_at} for item in ModelDeployment.objects.select_related('credential')])
        if resource == 'aliases':
            return Response([{'id': item.id, 'slug': item.slug, 'name': item.name, 'model_type': item.model_type, 'description': item.description, 'is_active': item.is_active} for item in ModelAlias.objects.all()])
        if resource == 'routes':
            return Response([{'id': item.id, 'alias_id': item.alias_id, 'alias': item.alias.slug, 'strategy': item.strategy, 'total_timeout_seconds': item.total_timeout_seconds, 'max_attempts': item.max_attempts, 'is_active': item.is_active, 'targets': [{'deployment_id': target.deployment_id, 'deployment': target.deployment.name, 'order': target.order, 'weight': target.weight, 'is_active': target.is_active} for target in item.targets.select_related('deployment').all()]} for item in RoutePolicy.objects.select_related('alias').prefetch_related('targets__deployment')])
        if resource == 'budgets':
            return Response([{'id': item.id, 'user_id': item.user_id, 'user_email': item.user.email, 'monthly_token_limit': item.monthly_token_limit, 'monthly_cost_limit': item.monthly_cost_limit, 'used_input_tokens': item.used_input_tokens, 'used_output_tokens': item.used_output_tokens, 'used_cost': item.used_cost, 'period_start': item.period_start, 'is_active': item.is_active} for item in UsageBudget.objects.select_related('user').order_by('-updated_at')[:300]])
        if resource == 'ledger':
            rows = ModelRequestLedger.objects.select_related('user', 'alias', 'deployment').order_by('-created_at')[:500]
            return Response([{'request_id': str(item.request_id), 'user_email': item.user.email if item.user else None, 'task_name': item.task_name, 'alias': item.alias.slug if item.alias else None, 'deployment': item.deployment.name if item.deployment else None, 'status': item.status, 'input_tokens': item.input_tokens, 'output_tokens': item.output_tokens, 'estimated_cost': item.estimated_cost, 'latency_ms': item.latency_ms, 'fallback_count': item.fallback_count, 'error_code': item.error_code, 'created_at': item.created_at} for item in rows])
        return Response({'code': 'gateway_resource_invalid', 'message': '不支持的网关资源。'}, status=404)

    def post(self, request, resource):
        from system.models import ModelAlias, ModelDeployment, ProviderCredential, RoutePolicy, RoutePolicyTarget
        reason, error = operation_reason(request, '模型网关配置必须填写原因。')
        if error:
            return error

        def execute():
            if resource == 'credentials':
                secret = str(request.data.get('secret') or '')
                if not secret:
                    return Response({'code': 'credential_secret_required', 'message': '必须提供凭据密钥。'}, status=400)
                item = ProviderCredential(name=request.data.get('name') or '', provider=request.data.get('provider') or 'openai_compatible', scope=ProviderCredential.Scope.PLATFORM)
                item.set_secret(secret)
                item.full_clean()
                item.save()
            elif resource == 'deployments':
                item = ModelDeployment.objects.create(
                    name=request.data.get('name') or '', provider=request.data.get('provider') or 'openai_compatible',
                    remote_model=request.data.get('remote_model') or '', model_type=request.data.get('model_type') or 'chat',
                    base_url=request.data.get('base_url') or '', credential_id=request.data.get('credential_id') or None,
                    context_window=int(request.data['context_window']) if request.data.get('context_window') else None,
                    tokenizer_family=str(request.data.get('tokenizer_family') or '').strip(),
                    tokenizer_name=str(request.data.get('tokenizer_name') or '').strip(),
                    priority=int(request.data.get('priority') or 100), timeout_seconds=int(request.data.get('timeout_seconds') or 30),
                )
            elif resource == 'aliases':
                item = ModelAlias.objects.create(slug=request.data.get('slug') or '', name=request.data.get('name') or '', model_type=request.data.get('model_type') or 'chat', description=request.data.get('description') or '')
            elif resource == 'routes':
                alias = ModelAlias.objects.filter(pk=request.data.get('alias_id')).first()
                if not alias:
                    return Response({'code': 'model_alias_required', 'message': '请选择有效模型别名。'}, status=400)
                item = RoutePolicy.objects.create(alias=alias, strategy=request.data.get('strategy') or RoutePolicy.Strategy.PRIORITY, total_timeout_seconds=int(request.data.get('total_timeout_seconds') or 45), max_attempts=int(request.data.get('max_attempts') or 2))
                for index, target in enumerate(request.data.get('targets') or []):
                    RoutePolicyTarget.objects.create(policy=item, deployment_id=target['deployment_id'], order=index, weight=int(target.get('weight') or 100))
            else:
                return Response({'code': 'gateway_resource_read_only', 'message': '该网关资源暂不支持创建。'}, status=405)
            audit(request, action=f'gateway.{resource}.create', resource_type=item.__class__.__name__, resource_id=item.pk, reason=reason, after={'name': getattr(item, 'name', getattr(item, 'slug', ''))})
            return Response({'id': item.pk, 'created': True}, status=201)

        return run_staff_idempotent(request, f'gateway_create:{resource}', execute)


class GatewayResourceAdminDetailView(StaffProtectedView):
    required_permissions = ['gateway.manage']

    def patch(self, request, resource, object_id):
        from system.models import ModelAlias, ModelDeployment, ProviderCredential, RoutePolicy
        reason, error = operation_reason(request, '修改模型网关配置必须填写原因。')
        if error:
            return error

        def execute():
            mapping = {'credentials': ProviderCredential, 'deployments': ModelDeployment, 'aliases': ModelAlias, 'routes': RoutePolicy}
            model = mapping.get(resource)
            item = model.objects.filter(pk=object_id).first() if model else None
            if not item:
                return Response({'code': 'gateway_resource_not_found', 'message': '网关资源不存在。'}, status=404)
            before = {'is_active': getattr(item, 'is_active', None), 'updated_at': getattr(item, 'updated_at', None)}
            allowed = {
                'credentials': ['name', 'provider', 'is_active'],
                'deployments': ['name', 'provider', 'remote_model', 'model_type', 'base_url', 'credential_id', 'context_window', 'tokenizer_family', 'tokenizer_name', 'priority', 'timeout_seconds', 'is_active'],
                'aliases': ['name', 'description', 'is_active'],
                'routes': ['strategy', 'total_timeout_seconds', 'max_attempts', 'is_active'],
            }[resource]
            for field in allowed:
                if field in request.data:
                    setattr(item, field, request.data[field])
            if resource == 'credentials' and request.data.get('secret'):
                item.set_secret(str(request.data['secret']))
            item.full_clean()
            item.save()
            audit(request, action=f'gateway.{resource}.update', resource_type=item.__class__.__name__, resource_id=item.pk, reason=reason, before=before, after={'is_active': getattr(item, 'is_active', None)})
            return Response({'id': item.pk, 'updated': True})

        return run_staff_idempotent(request, f'gateway_update:{resource}:{object_id}', execute)


class AnalyticsAdminView(StaffProtectedView):
    required_permissions = ['analytics.view']

    def get(self, request):
        from careers.models import JobApplication
        from core.models import AsyncOperation
        from interviews.models import InterviewSession
        from knowledge.models import KnowledgeDocument
        from system.models import ModelRequestLedger
        from users.models import User
        since = timezone.now() - timedelta(days=30)
        ledgers = ModelRequestLedger.objects.filter(created_at__gte=since)
        return Response({
            'period_days': 30,
            'candidate_total': User.objects.filter(role=User.Role.CANDIDATE).count(),
            'candidate_new': User.objects.filter(role=User.Role.CANDIDATE, date_joined__gte=since).count(),
            'interviews': dict(InterviewSession.objects.filter(created_at__gte=since).values_list('status').annotate(total=Count('id'))),
            'applications': dict(JobApplication.objects.filter(created_at__gte=since).values_list('status').annotate(total=Count('id'))),
            'knowledge': {
                'published': KnowledgeDocument.objects.filter(approval_status=KnowledgeDocument.ApprovalStatus.APPROVED, status=KnowledgeDocument.Status.INDEXED).count(),
                'retrievals': KnowledgeDocument.objects.aggregate(total=Sum('retrieval_count'))['total'] or 0,
            },
            'model': ledgers.aggregate(
                requests=Count('id'), failures=Count('id', filter=models.Q(status=ModelRequestLedger.Status.FAILED)),
                input_tokens=Sum('input_tokens'), output_tokens=Sum('output_tokens'), cost=Sum('estimated_cost'),
            ),
            'tasks': dict(AsyncOperation.objects.filter(created_at__gte=since).values_list('status').annotate(total=Count('id'))),
        })


class FeatureFlagAdminView(StaffProtectedView):
    required_permissions = ['feature_flags.manage']

    def get(self, request):
        return Response([{'id': item.id, 'key': item.key, 'name': item.name, 'description': item.description, 'enabled': item.enabled, 'rollout_percentage': item.rollout_percentage, 'audience': item.audience, 'version': item.version, 'updated_at': item.updated_at} for item in PlatformFeatureFlag.objects.order_by('key')])

    def post(self, request):
        reason, error = operation_reason(request, '创建功能开关必须填写原因。')
        if error:
            return error

        def execute():
            item = PlatformFeatureFlag.objects.create(
                key=request.data.get('key') or '', name=request.data.get('name') or '',
                description=request.data.get('description') or '', enabled=bool(request.data.get('enabled')),
                rollout_percentage=max(0, min(100, int(request.data.get('rollout_percentage') or 0))),
                audience=request.data.get('audience') or {}, updated_by=request.user,
            )
            audit(request, action='feature_flag.create', resource_type='PlatformFeatureFlag', resource_id=item.id, reason=reason, after={'key': item.key, 'enabled': item.enabled})
            return Response({'id': item.id}, status=201)

        return run_staff_idempotent(request, 'feature_flag_create', execute)


class FeatureFlagAdminDetailView(StaffProtectedView):
    required_permissions = ['feature_flags.manage']

    def patch(self, request, flag_id):
        reason, error = operation_reason(request, '修改功能开关必须填写原因。')
        if error:
            return error

        def execute():
            item = PlatformFeatureFlag.objects.filter(pk=flag_id).first()
            if not item:
                return Response({'code': 'feature_flag_not_found', 'message': '功能开关不存在。'}, status=404)
            before = {'enabled': item.enabled, 'rollout_percentage': item.rollout_percentage, 'version': item.version}
            for field in ['name', 'description', 'enabled', 'rollout_percentage', 'audience']:
                if field in request.data:
                    setattr(item, field, request.data[field])
            item.rollout_percentage = max(0, min(100, int(item.rollout_percentage)))
            item.version += 1
            item.updated_by = request.user
            item.save()
            audit(request, action='feature_flag.update', resource_type='PlatformFeatureFlag', resource_id=item.id, reason=reason, before=before, after={'enabled': item.enabled, 'rollout_percentage': item.rollout_percentage, 'version': item.version})
            return Response({'id': item.id, 'version': item.version, 'enabled': item.enabled})

        return run_staff_idempotent(request, f'feature_flag_update:{flag_id}', execute)


class ContentOperationsAdminView(StaffProtectedView):
    required_permissions = ['content.manage']

    def get(self, request):
        from blog.models import Post
        from community.models import CommunityTopicLink, CommunityWebhookEvent
        return Response({
            'posts': [{'id': item.id, 'title': item.title, 'status': item.status, 'is_featured': item.is_featured, 'author': item.author.email, 'published_at': item.published_at, 'updated_at': item.updated_at} for item in Post.objects.select_related('author').order_by('-updated_at')[:200]],
            'community_topics': CommunityTopicLink.objects.count(),
            'failed_webhooks': CommunityWebhookEvent.objects.filter(status=CommunityWebhookEvent.Status.FAILED).count(),
        })

    def post(self, request):
        from community.operation_handlers import create_search_rebuild_operation
        reason, error = operation_reason(request, '内容索引操作必须填写原因。')
        if error:
            return error

        def execute():
            principal = staff_operation_principal(request.user)
            if not principal:
                return Response({
                    'code': 'staff_operation_principal_missing',
                    'message': '当前员工账号未绑定同邮箱的平台管理员业务账号，无法创建全局异步 Operation。',
                }, status=409)
            with transaction.atomic():
                operation = create_search_rebuild_operation(user=principal)
                audit(
                    request,
                    action='content.search.rebuild',
                    resource_type='Meilisearch',
                    reason=reason,
                    after={'operation_id': str(operation.pk)},
                )
            return Response(operation_envelope(
                operation,
                queued=True,
                task_id=str(operation.pk),
            ), status=202)

        return run_staff_idempotent(request, 'content_search_rebuild', execute)


class NotificationOperationsAdminView(StaffProtectedView):
    required_permissions = ['notifications.manage']

    def get(self, request):
        from notifications.models import NotificationOutbox
        from staff_admin.models import StaffEmailOutbox
        return Response({
            'candidate_outbox': [{'event_id': str(item.event_id), 'status': item.status, 'attempts': item.attempts, 'last_error': item.last_error, 'created_at': item.created_at, 'published_at': item.published_at} for item in NotificationOutbox.objects.order_by('-created_at')[:200]],
            'staff_email_outbox': [{'id': str(item.id), 'to_email': item.to_email, 'status': item.status, 'attempts': item.attempts, 'last_error': item.last_error, 'created_at': item.created_at, 'sent_at': item.sent_at} for item in StaffEmailOutbox.objects.order_by('-created_at')[:200]],
        })


class MaintenanceNoticeAdminView(StaffProtectedView):
    required_permissions = ['feature_flags.manage']

    def get(self, request):
        return Response([{'id': item.id, 'title': item.title, 'content': item.content, 'status': item.status, 'starts_at': item.starts_at, 'ends_at': item.ends_at, 'updated_at': item.updated_at} for item in MaintenanceNotice.objects.order_by('-updated_at')])

    def post(self, request):
        reason, error = operation_reason(request, '创建维护公告必须填写原因。')
        if error:
            return error

        def execute():
            item = MaintenanceNotice.objects.create(
                title=request.data.get('title') or '', content=request.data.get('content') or '',
                status=request.data.get('status') or MaintenanceNotice.Status.DRAFT,
                starts_at=request.data.get('starts_at') or None, ends_at=request.data.get('ends_at') or None,
                created_by=request.user,
            )
            audit(request, action='maintenance_notice.create', resource_type='MaintenanceNotice', resource_id=item.id, reason=reason, after={'title': item.title, 'status': item.status})
            return Response({'id': item.id}, status=201)

        return run_staff_idempotent(request, 'maintenance_notice_create', execute)
