# ai_interview_backend/interviews/views.py

import json
import hashlib
from django.conf import settings
from django.utils import timezone
from django.http import StreamingHttpResponse
from django.core.cache import cache
from django.db import IntegrityError, transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from core.idempotency import run_idempotent
from core.throttles import AIActionRateThrottle
from rest_framework.views import APIView
from resumes.models import Resume, ResumeImportJob, ResumeVersion
from resumes.json_resume import json_resume_plain_text
from careers.models import JobTarget
from knowledge.services import RequiredRAGContextUnavailable
from staff_admin.feature_flags import feature_flag_enabled
from system.models import AISetting
from users.models import User
from .evaluation import (
    build_session_plan,
    can_manage_interview_system,
    combine_rule_and_ai_evaluation,
    ensure_default_interview_assets,
    rule_evaluate_answer,
    select_interview_template,
    summarize_report_scores,
    update_session_coverage,
    validate_generated_question,
)
from .models import (
    EvaluationDataset,
    EvaluationRun,
    InterviewAgentExecution,
    InterviewAgentMemoryEvent,
    InterviewAgentRun,
    InterviewAgentToolCall,
    InterviewAgentTrace,
    InterviewCalibrationCase,
    InterviewMediaArtifact,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewReferenceAnswer,
    InterviewRubric,
    InterviewSession,
    InterviewTemplate,
)
from .execution import create_answer_execution, durable_execution_snapshot, short_lock_timeout
from .serializers import (
    InterviewSessionSerializer,
    StartInterviewSerializer,
    SubmitAnswerSerializer,
    FinishInterviewSerializer,
    EvaluationDatasetSerializer,
    EvaluationRunSerializer,
    InterviewAgentMemoryEventSerializer,
    InterviewAgentExecutionSerializer,
    InterviewAgentRunSerializer,
    InterviewAgentToolCallSerializer,
    InterviewAgentTraceSerializer,
    InterviewCalibrationCaseSerializer,
    InterviewMediaArtifactSerializer,
    InterviewQuestionGenerationJobSerializer,
    InterviewRubricSerializer,
    RegenerateNextQuestionSerializer,
    InterviewTemplateSerializer,
)
from .ai_services import (
    polish_description_by_ai,
    generate_reference_answer_for_question,
)
from .agent import get_interview_agent_engine
from .configuration import assemble_generation_context, resolve_agent_config, stable_hash
from .agent_v4.events import publish_agent_event, read_agent_events
from .speech_services import synthesize_question_tts
from urllib.parse import quote

def format_resume_to_text(resume: Resume) -> str:
    """
    一个统一的函数，从任何类型的 Resume 实例中提取纯文本内容。
    """
    # 优先级 1: 新的 content_json (无论是对象还是数组)
    if resume.content_json:
        components = []
        # 兼容新的二维布局对象
        if isinstance(resume.content_json, dict) and 'main' in resume.content_json:
            components.extend(resume.content_json.get('sidebar', []))
            components.extend(resume.content_json.get('main', []))
        # 兼容旧的一维数组
        elif isinstance(resume.content_json, list):
            components = resume.content_json

        all_text = []
        for module in components:
            if not module or not isinstance(module, dict): continue
            props = module.get('props', {})
            if not props or not isinstance(props, dict): continue

            all_text.append(f"\n--- {props.get('title', module.get('title', ''))} ---\n")

            # 提取简单 props
            for key, value in props.items():
                if isinstance(value, str) and key not in ['title', 'layoutZone', 'titleStyle']:
                    all_text.append(value)

            # 提取列表型 props
            for list_key in ['items', 'educations', 'experiences', 'projects', 'skills']:
                if list_key in props and isinstance(props[list_key], list):
                    for item in props[list_key]:
                        if not item or not isinstance(item, dict): continue
                        item_texts = []
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str) and item_key != 'id':
                                item_texts.append(item_value)
                        all_text.append(" ".join(item_texts))

        return "\n".join(filter(None, all_text))

    # 优先级 2: 文件简历的解析内容
    if resume.parsed_content:
        return resume.parsed_content

    # 优先级 3: 旧版的、基于模型字段的在线简历
    # (这个逻辑可以逐步废弃，但为了兼容性暂时保留)
    if resume.status in [Resume.Status.DRAFT, Resume.Status.PUBLISHED]:
        parts = []
        if resume.full_name: parts.append(f"姓名: {resume.full_name}")
        if resume.job_title: parts.append(f"期望职位: {resume.job_title}")
        if resume.summary: parts.append(f"\n个人总结:\n{resume.summary}")
        return "\n".join(parts)

    return ""


def get_user_cache_key(user):
    return f"user_{user.id}_unfinished_interview"


class InterviewSystemManageMixin:
    permission_classes = [permissions.IsAuthenticated]

    def _ensure_manager(self):
        if not can_manage_interview_system(self.request.user):
            raise PermissionDenied('只有管理员或HR可以管理企业面试体系。')

    def perform_create(self, serializer):
        self._ensure_manager()
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        self._ensure_manager()
        instance = self.get_object()
        if getattr(instance, 'visibility', '') == 'system':
            raise PermissionDenied('系统内置对象只能复制后编辑。')
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_manager()
        if getattr(instance, 'visibility', '') == 'system':
            raise PermissionDenied('系统内置对象不能删除。')
        instance.delete()


class InterviewTemplateViewSet(InterviewSystemManageMixin, viewsets.ModelViewSet):
    serializer_class = InterviewTemplateSerializer

    def get_queryset(self):
        ensure_default_interview_assets()
        queryset = InterviewTemplate.objects.select_related('rubric', 'created_by').prefetch_related(
            'stages',
            'rubric__dimensions',
            'rubric__dimensions__anchors',
        )
        user = self.request.user
        if can_manage_interview_system(user):
            return queryset
        return queryset.filter(is_active=True)

    @action(detail=True, methods=['post'], url_path='clone')
    def clone(self, request, pk=None):
        self._ensure_manager()
        source = self.get_object()
        source_snapshot = {
            'name': source.name,
            'description': source.description,
            'job_keywords': source.job_keywords,
            'visibility': InterviewTemplate.Visibility.PRIVATE,
            'is_active': True,
            'version': 1,
            'require_rag': source.require_rag,
            'config': source.config,
            'rubric': source.rubric_id,
            'stages': [
                {
                    'stage_key': stage.stage_key,
                    'name': stage.name,
                    'order': stage.order,
                    'question_ratio': stage.question_ratio,
                    'target_dimensions': stage.target_dimensions,
                    'question_guidance': stage.question_guidance,
                }
                for stage in source.stages.all()
            ],
        }
        serializer = self.get_serializer(data={
            **source_snapshot,
            'name': f'{source.name} 副本',
        })
        serializer.is_valid(raise_exception=True)
        clone = serializer.save(created_by=request.user)
        return Response(self.get_serializer(clone).data, status=status.HTTP_201_CREATED)


class InterviewRubricViewSet(InterviewSystemManageMixin, viewsets.ModelViewSet):
    serializer_class = InterviewRubricSerializer

    def get_queryset(self):
        ensure_default_interview_assets()
        queryset = InterviewRubric.objects.prefetch_related('dimensions', 'dimensions__anchors').select_related('created_by')
        if can_manage_interview_system(self.request.user):
            return queryset
        return queryset.filter(is_active=True)


class InterviewCalibrationCaseViewSet(InterviewSystemManageMixin, viewsets.ModelViewSet):
    serializer_class = InterviewCalibrationCaseSerializer

    def get_queryset(self):
        queryset = InterviewCalibrationCase.objects.select_related('rubric', 'created_by')
        if can_manage_interview_system(self.request.user):
            return queryset
        return queryset.none()


class EvaluationDatasetViewSet(InterviewSystemManageMixin, viewsets.ModelViewSet):
    serializer_class = EvaluationDatasetSerializer

    def get_queryset(self):
        queryset = EvaluationDataset.objects.prefetch_related('cases').select_related('created_by')
        if can_manage_interview_system(self.request.user):
            return queryset
        return queryset.none()


class EvaluationRunViewSet(viewsets.ModelViewSet):
    serializer_class = EvaluationRunSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = EvaluationRun.objects.select_related('dataset', 'template', 'created_by').prefetch_related('metrics')
        if can_manage_interview_system(self.request.user):
            return queryset
        return queryset.none()

    def perform_create(self, serializer):
        if not can_manage_interview_system(self.request.user):
            raise PermissionDenied('只有管理员或HR可以运行离线评估。')
        run = serializer.save(created_by=self.request.user)
        try:
            from .tasks import run_evaluation_run
            run_evaluation_run.delay(run.id)
        except Exception:
            from .evaluation import run_offline_rule_evaluation
            run_offline_rule_evaluation(run)


class InterviewSessionViewSet(viewsets.ModelViewSet):
    queryset = InterviewSession.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InterviewSessionSerializer

    def _agent(self):
        return get_interview_agent_engine()

    def get_queryset(self):
        queryset = InterviewSession.objects.all()
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def _trace_agent_turn(
        self,
        *,
        session: InterviewSession,
        event: str,
        question: InterviewQuestion | None = None,
        answer_evaluation: dict | None = None,
        rag_context: list | None = None,
        question_plan: dict | None = None,
        generated_question: str = '',
        fallback_reason: str = '',
        extra_outputs: dict | None = None,
    ) -> None:
        node_outputs = {
            'load_context': {
                'stage': session.current_stage,
                'pending_topics': session.pending_topics,
                'covered_topics': session.covered_topics,
            },
            'evaluate_answer': answer_evaluation or {},
            'retrieve_knowledge': {
                'source_count': len(rag_context or []),
                'sources': [
                    {
                        'document_id': item.get('document_id'),
                        'chunk_id': item.get('chunk_id'),
                        'title': item.get('title'),
                        'visibility': item.get('visibility'),
                        'ability_tags': item.get('ability_tags'),
                        'score': item.get('score'),
                    }
                    for item in (rag_context or [])[:6]
                    if isinstance(item, dict)
                ],
            },
            'plan_next_question': question_plan or {},
            'generate_question': {'question_text': generated_question},
        }
        if extra_outputs:
            node_outputs.update(extra_outputs)
        InterviewAgentTrace.objects.create(
            session=session,
            question=question,
            event=event,
            stage=session.current_stage or '',
            node_outputs=node_outputs,
            answer_evaluation=answer_evaluation or {},
            rag_context=rag_context or [],
            question_plan=question_plan or {},
            generated_question=generated_question or '',
            fallback_reason=fallback_reason or '',
            input_hash=hashlib.sha256(json.dumps(node_outputs, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest(),
            output_summary={
                'generated_question_length': len(generated_question or ''),
                'final_score': (answer_evaluation or {}).get('final_score'),
                'evaluation_mode': (answer_evaluation or {}).get('evaluation_mode'),
            },
            validation_errors=(extra_outputs or {}).get('validation_errors', []),
            model_config_snapshot=(session.session_plan or {}).get('model_config_snapshot', {}),
        )

    @action(detail=True, methods=['get'], url_path='agent-traces')
    def agent_traces(self, request, pk=None):
        session = self.get_object()
        traces = session.agent_traces.select_related('question').order_by('created_at')
        serializer = InterviewAgentTraceSerializer(traces, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='agent-tool-calls')
    def agent_tool_calls(self, request, pk=None):
        session = self.get_object()
        calls = session.agent_tool_calls.select_related('question', 'trace').order_by('created_at')
        serializer = InterviewAgentToolCallSerializer(calls, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='agent-memory-events')
    def agent_memory_events(self, request, pk=None):
        session = self.get_object()
        events = session.agent_memory_events.select_related('question', 'trace').order_by('created_at')
        serializer = InterviewAgentMemoryEventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='agent-runs')
    def agent_runs(self, request, pk=None):
        session = self.get_object()
        runs = session.agent_runs.select_related('trigger_question').order_by('-created_at')
        serializer = InterviewAgentRunSerializer(runs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='agent-executions')
    def agent_executions(self, request, pk=None):
        session = self.get_object()
        executions = session.agent_executions.select_related(
            'trigger_question', 'legacy_run'
        ).order_by('-created_at')
        return Response(
            InterviewAgentExecutionSerializer(executions, many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=['get'],
        url_path=r'agent-executions/(?P<run_id>[0-9a-f-]+)/events',
    )
    def agent_execution_events(self, request, pk=None, run_id=None):
        session = self.get_object()
        execution = session.agent_executions.filter(run_id=run_id).first()
        if not execution:
            return Response({'error': 'Agent执行不存在'}, status=status.HTTP_404_NOT_FOUND)

        after = request.headers.get('Last-Event-ID') or request.query_params.get('after') or '0-0'
        follow = str(request.query_params.get('follow', '')).lower() in ('1', 'true', 'yes')

        def event_generator():
            cursor = after
            empty_reads = 0
            emitted_durable_snapshot = False
            while True:
                try:
                    events = list(read_agent_events(
                        run_id=execution.run_id,
                        after=cursor,
                        block_ms=5000 if follow else 0,
                        count=100,
                    ))
                except Exception:
                    events = []
                if not events:
                    empty_reads += 1
                    if not emitted_durable_snapshot:
                        from .agent_v4.events import durable_snapshot_event
                        execution.refresh_from_db()
                        snapshot = durable_snapshot_event(execution)
                        emitted_durable_snapshot = True
                        cursor = snapshot.event_id
                        yield snapshot.to_sse()
                    if not follow or empty_reads >= 3:
                        break
                    yield ': heartbeat\n\n'
                    continue
                empty_reads = 0
                for event in events:
                    cursor = event.event_id
                    yield event.to_sse()
                execution.refresh_from_db(fields=['status'])
                if execution.status in (
                    InterviewAgentExecution.Status.COMPLETED,
                    InterviewAgentExecution.Status.DEGRADED,
                    InterviewAgentExecution.Status.FAILED,
                    InterviewAgentExecution.Status.FAILED_RETRYABLE,
                    InterviewAgentExecution.Status.FAILED_TERMINAL,
                    InterviewAgentExecution.Status.CANCELED,
                ):
                    break

        response = StreamingHttpResponse(event_generator(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        return response

    @action(detail=True, methods=['get'], url_path='resume-state')
    def resume_state(self, request, pk=None):
        session = self.get_object()
        execution = session.agent_executions.select_related(
            'trigger_question', 'result_question'
        ).order_by('-created_at').first()
        current_question = session.questions.filter(answered_at__isnull=True).order_by('sequence').first()
        if not current_question and execution and execution.result_question_id:
            current_question = execution.result_question
        latest_answered = session.questions.filter(answered_at__isnull=False).order_by('-sequence').first()

        if session.status != InterviewSession.Status.RUNNING:
            resume_action = 'finish'
        elif execution and execution.status in (
            InterviewAgentExecution.Status.ACCEPTED,
            InterviewAgentExecution.Status.ANSWER_PERSISTED,
            InterviewAgentExecution.Status.EVALUATING,
            InterviewAgentExecution.Status.EVALUATED,
            InterviewAgentExecution.Status.GENERATING,
            InterviewAgentExecution.Status.PENDING,
            InterviewAgentExecution.Status.RUNNING,
            InterviewAgentExecution.Status.WAITING,
        ):
            resume_action = 'wait'
        elif execution and execution.status in (
            InterviewAgentExecution.Status.FAILED_RETRYABLE,
            InterviewAgentExecution.Status.FAILED,
        ):
            resume_action = 'retry_generation'
        elif execution and execution.status == InterviewAgentExecution.Status.FAILED_TERMINAL:
            resume_action = 'finish'
        else:
            resume_action = 'continue'

        return Response({
            'session_id': str(session.id),
            'session_status': session.status,
            'resume_action': resume_action,
            'current_question': self._serialize_question(current_question) if current_question else None,
            'latest_evaluation': (
                latest_answered.ai_feedback
                if latest_answered and isinstance(latest_answered.ai_feedback, dict)
                else None
            ),
            'execution': durable_execution_snapshot(execution) if execution else None,
            'updated_at': session.updated_at,
        })

    @action(detail=True, methods=['get'], url_path=r'agent-runs/(?P<run_id>[0-9a-f-]+)')
    def agent_run_detail(self, request, pk=None, run_id=None):
        session = self.get_object()
        try:
            run = session.agent_runs.select_related('trigger_question').prefetch_related('node_runs').get(id=run_id)
        except InterviewAgentRun.DoesNotExist:
            return Response({'error': 'Agent运行不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = InterviewAgentRunSerializer(run, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='question-generation-jobs')
    def question_generation_jobs(self, request, pk=None):
        session = self.get_object()
        jobs = session.question_generation_jobs.select_related(
            'answered_question',
            'generated_question',
        ).order_by('-created_at')
        serializer = InterviewQuestionGenerationJobSerializer(jobs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='media-artifacts')
    def media_artifacts(self, request, pk=None):
        session = self.get_object()
        artifacts = session.media_artifacts.select_related('question').order_by('-created_at')
        serializer = InterviewMediaArtifactSerializer(artifacts, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path=r'questions/(?P<question_id>\d+)/tts')
    def question_tts(self, request, pk=None, question_id=None):
        session = self.get_object()
        try:
            question = session.questions.get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return Response({'error': '问题不存在'}, status=status.HTTP_404_NOT_FOUND)

        result = synthesize_question_tts(
            session=session,
            question=question,
            user=request.user,
            text=question.question_text,
        )
        if not result.ok or not result.artifact:
            return Response({
                'status': 'failed',
                'fallback': 'browser_tts',
                'error': result.error or 'tts_failed',
                'artifact_id': str(result.artifact.id) if result.artifact else '',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = InterviewMediaArtifactSerializer(result.artifact, context={'request': request})
        return Response({
            'status': 'completed',
            'artifact': serializer.data,
            'audio_url': serializer.data.get('file_url'),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='check-unfinished')
    def check_unfinished(self, request):
        cache_key = get_user_cache_key(request.user)
        sessions = list(
            InterviewSession.objects.filter(user=request.user, status=InterviewSession.Status.RUNNING)
            .order_by('-last_activity_at', '-updated_at', '-created_at')
        )
        if not sessions:
            cache.delete(cache_key)
            return Response({"has_unfinished": False}, status=status.HTTP_200_OK)

        session = sessions[0]
        cache.set(cache_key, str(session.id), timeout=7200)
        return Response({
            "has_unfinished": True,
            "session_id": session.id,
            "job_position": session.job_position,
            "conflict": len(sessions) > 1,
            "sessions": [
                {
                    "session_id": item.id,
                    "job_position": item.job_position,
                    "last_activity_at": item.last_activity_at or item.updated_at,
                }
                for item in sessions
            ],
        }, status=status.HTTP_200_OK)

    def _abandon_session(self, request, session_id):
        cache_key = get_user_cache_key(request.user)
        with transaction.atomic():
            request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            try:
                session = InterviewSession.objects.select_for_update().get(
                    id=session_id, user=request.user
                )
            except InterviewSession.DoesNotExist:
                return Response({"error": "面试会话不存在"}, status=status.HTTP_404_NOT_FOUND)
            if session.status == InterviewSession.Status.CANCELED:
                return Response({"message": "面试已放弃", "session_id": session.id})
            if session.status != InterviewSession.Status.RUNNING:
                return Response(
                    {"error": "只有进行中的面试可以放弃", "session_id": session.id, "status": session.status},
                    status=status.HTTP_409_CONFLICT,
                )
            now = timezone.now()
            session.status = InterviewSession.Status.CANCELED
            session.finished_at = now
            session.last_activity_at = now
            session.save(update_fields=['status', 'finished_at', 'last_activity_at', 'updated_at'])
        if str(cache.get(cache_key) or '') == str(session.id):
            cache.delete(cache_key)
        return Response({"message": "面试已放弃", "session_id": session.id}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='abandon')
    def abandon(self, request, pk=None):
        return self._abandon_session(request, pk)

    @action(detail=False, methods=['post'], url_path='abandon-unfinished')
    def abandon_unfinished(self, request):
        sessions = list(
            InterviewSession.objects.filter(user=request.user, status=InterviewSession.Status.RUNNING)
            .order_by('-last_activity_at', '-updated_at', '-created_at')
        )
        requested_id = request.data.get('session_id')
        if requested_id:
            return self._abandon_session(request, requested_id)
        if not sessions:
            cache.delete(get_user_cache_key(request.user))
            return Response({"message": "没有需要放弃的面试"}, status=status.HTTP_404_NOT_FOUND)
        if len(sessions) > 1:
            return Response({
                "error": "存在多个进行中的面试，请指定 session_id",
                "code": "multiple_running_sessions",
                "sessions": [{"session_id": item.id, "job_position": item.job_position} for item in sessions],
            }, status=status.HTTP_409_CONFLICT)
        return self._abandon_session(request, sessions[0].id)

    @action(detail=False, methods=['post'], url_path='start', throttle_classes=[AIActionRateThrottle])
    def start_interview(self, request):
        return run_idempotent(
            request,
            'interview_start',
            lambda: self._start_interview_impl(request),
        )

    def _start_interview_impl(self, request, overrides=None):
        force_start = request.query_params.get('force', 'false').lower() == 'true'
        cache_key = get_user_cache_key(request.user)
        running_sessions = list(
            InterviewSession.objects.filter(user=request.user, status=InterviewSession.Status.RUNNING)
            .order_by('-last_activity_at', '-updated_at', '-created_at')
        )
        if running_sessions and not force_start:
            return Response({
                "error": "您有正在进行的面试",
                "code": "unfinished_interview_exists",
                "sessions": [{"session_id": item.id, "job_position": item.job_position} for item in running_sessions],
            }, status=status.HTTP_409_CONFLICT)
        serializer = StartInterviewSerializer(data={**request.data, **(overrides or {})})
        serializer.is_valid(raise_exception=True)
        job_position = serializer.validated_data.get('job_position', '').strip()
        jd_text = serializer.validated_data.get('jd_text', '').strip()
        resume_id = serializer.validated_data.get('resume_id')
        resume_version_id = serializer.validated_data.get('resume_version_id')
        job_target_id = serializer.validated_data.get('job_target_id')
        question_count = serializer.validated_data.get('question_count')
        target_duration_minutes = serializer.validated_data.get('target_duration_minutes')
        interview_mode = serializer.validated_data.get('interview_mode') or ''
        experience_mode = serializer.validated_data.get('experience_mode')
        recording_enabled = serializer.validated_data.get('recording_enabled', False)
        template_id = serializer.validated_data.get('template_id')

        job_target = None
        if job_target_id:
            from careers.models import JobTarget
            try:
                job_target = JobTarget.objects.get(id=job_target_id, user=request.user)
            except JobTarget.DoesNotExist:
                return Response({"error": "求职目标不存在"}, status=status.HTTP_404_NOT_FOUND)
            job_position = job_position or job_target.position_name
            jd_text = jd_text or job_target.jd_text

        resume_text = ""
        resume_instance = None
        resume_version = None
        resume_snapshot = {}
        if resume_version_id:
            from resumes.models import ResumeVersion
            from resumes.json_resume import json_resume_plain_text
            try:
                resume_version = ResumeVersion.objects.select_related('resume').get(
                    id=resume_version_id,
                    resume__user=request.user,
                )
            except ResumeVersion.DoesNotExist:
                return Response({"error": "简历版本不存在"}, status=status.HTTP_404_NOT_FOUND)
            resume_instance = resume_version.resume
            resume_snapshot = resume_version.resume_json
            resume_text = json_resume_plain_text(resume_snapshot)
        elif resume_id:
            try:
                resume_instance = Resume.objects.get(id=resume_id, user=request.user)
                from resumes.versioning import ensure_resume_version
                from resumes.json_resume import json_resume_plain_text
                resume_version = ensure_resume_version(resume_instance, request.user)
                resume_snapshot = resume_version.resume_json
                resume_text = json_resume_plain_text(resume_snapshot)
                print("已为面试提取简历文本。")
            except Resume.DoesNotExist:
                return Response({"error": "简历不存在"}, status=status.HTTP_404_NOT_FOUND)

        agent = self._agent()
        template = select_interview_template(
            job_position,
            jd_text=jd_text,
            template_id=template_id,
            user=request.user,
        )
        session_plan, template_snapshot = build_session_plan(
            template=template,
            question_count=question_count,
            job_position=job_position,
            jd_text=jd_text,
            target_duration_minutes=target_duration_minutes,
            interview_mode=interview_mode,
            experience_mode=experience_mode,
        )
        candidate_agent_config = resolve_agent_config(template)
        config_enabled = feature_flag_enabled(
            'agent-config-new-sessions',
            subject=request.user,
            default=False,
        )
        shadow_enabled = feature_flag_enabled(
            'agent-config-shadow',
            subject=request.user,
            default=False,
        )
        agent_config_snapshot = candidate_agent_config if config_enabled else {}
        rollout_snapshot = {
            'shadow_enabled': shadow_enabled,
            'control_plane_enabled': config_enabled,
            'candidate_config_hash': candidate_agent_config.get('config_hash') or '',
            'candidate_revision_ids': candidate_agent_config.get('revision_ids') or [],
            'candidate_prompt_hashes': candidate_agent_config.get('prompt_hashes') or {},
            'candidate_knowledge_revision_ids': [
                item.get('knowledge_base_revision_id')
                for item in candidate_agent_config.get('knowledge_bindings') or []
            ],
            'legacy': {
                'prompt_version': getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1'),
                'context_token_budget': getattr(settings, 'AGENT_CONTEXT_TOKEN_BUDGET', 6000),
                'hybrid_search_topk': getattr(settings, 'HYBRID_SEARCH_TOPK', 4),
            },
        }
        rollout_snapshot['comparison_hash'] = stable_hash(rollout_snapshot)
        if shadow_enabled or config_enabled:
            template_snapshot = {
                **template_snapshot,
                'agent_config_rollout': rollout_snapshot,
            }
        initial_memory, initial_pending_topics = agent.build_initial_memory(
            job_position,
            resume_text=resume_text,
            jd_text=jd_text
        )

        first_question_text = agent.generate_first_question(
            job_position=job_position,
            user=request.user,
            resume_text=resume_text,
            difficulty=InterviewSession.Difficulty.MEDIUM,
            jd_text=jd_text,
            agent_config_snapshot=agent_config_snapshot,
        )
        with transaction.atomic():
            request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            locked_running = list(
                InterviewSession.objects.select_for_update().filter(
                    user=request.user,
                    status=InterviewSession.Status.RUNNING,
                ).order_by('-last_activity_at', '-updated_at', '-created_at')
            )
            if locked_running and not force_start:
                return Response({
                    "error": "您有正在进行的面试",
                    "code": "unfinished_interview_exists",
                    "sessions": [
                        {"session_id": item.id, "job_position": item.job_position}
                        for item in locked_running
                    ],
                }, status=status.HTTP_409_CONFLICT)
            if locked_running:
                now = timezone.now()
                InterviewSession.objects.filter(id__in=[item.id for item in locked_running]).update(
                    status=InterviewSession.Status.CANCELED,
                    finished_at=now,
                    last_activity_at=now,
                )

            now = timezone.now()
            session = InterviewSession.objects.create(
                user=request.user, job_position=job_position, resume=resume_instance,
                resume_version=resume_version, job_target=job_target,
                resume_snapshot=resume_snapshot, jd_snapshot=jd_text,
                question_count=question_count, status=InterviewSession.Status.RUNNING, started_at=now,
                last_activity_at=now,
                target_duration_minutes=target_duration_minutes,
                experience_mode=experience_mode,
                interview_mode=interview_mode or template.interview_mode,
                progress_mode='time_and_coverage' if getattr(agent, 'engine_name', '') == 'composite_v3' else 'question_count',
                recording_enabled=recording_enabled,
                template=template,
                session_plan=session_plan,
                template_snapshot=template_snapshot,
                agent_config_snapshot=agent_config_snapshot,
                coverage_summary={'coverage': {}, 'coverage_gaps': session_plan.get('coverage_gaps', [])},
                current_stage=InterviewSession.InterviewStage.OPENING,
                memory_summary=initial_memory,
                covered_topics=[],
                pending_topics=initial_pending_topics,
                perception_summary={}
            )
            InterviewQuestion.objects.create(
                session=session,
                question_text=first_question_text,
                sequence=1,
                question_plan={
                    'stage': InterviewSession.InterviewStage.OPENING,
                    'target_stage': InterviewSession.InterviewStage.SELF_INTRO,
                    'target_dimension': '',
                    'next_action': 'ASK_NEW',
                    'topic_id': 'self_intro',
                    'parent_topic_id': '',
                    'followup_depth': 0,
                    'answer_state': '',
                    'dialogue_act': 'opening',
                    'stage_entry_reason': 'interview_started',
                    'stage_exit_reason': '',
                },
                generation_mode='deterministic_opening',
                validation_status='validated',
            )
            if hasattr(agent, 'remember_generated_question'):
                session.memory_summary = agent.remember_generated_question(session.memory_summary, first_question_text)
                session.save(update_fields=['memory_summary', 'updated_at'])
        cache.delete(cache_key)
        cache.set(cache_key, str(session.id), timeout=7200)
        session_data = self.get_serializer(instance=session).data
        return Response(session_data, status=status.HTTP_201_CREATED)

    def _serialize_question(self, question: InterviewQuestion) -> dict:
        realistic = question.session.experience_mode == InterviewSession.ExperienceMode.REALISTIC
        return {
            "id": question.id,
            "question_text": question.question_text,
            "sequence": question.sequence,
            "answer_text": question.answer_text,
            "ai_feedback": None if realistic else question.ai_feedback,
            "analysis_data": question.analysis_data,
            "rag_context": [] if realistic else question.rag_context,
            "question_plan": {} if realistic else question.question_plan,
            "target_dimension": '' if realistic else question.target_dimension,
            "generation_mode": question.generation_mode,
            "validation_status": question.validation_status,
        }

    def _set_agent_run_header(self, response, run_id):
        if run_id:
            response['X-Agent-Run-Id'] = str(run_id)
            exposed = response.get('Access-Control-Expose-Headers', '')
            headers = [item.strip() for item in exposed.split(',') if item.strip()]
            if 'X-Agent-Run-Id' not in headers:
                headers.append('X-Agent-Run-Id')
            response['Access-Control-Expose-Headers'] = ', '.join(headers)
        return response

    def _generation_request_hash(self, session: InterviewSession, question: InterviewQuestion, answer_text: str) -> str:
        payload = {
            'session_id': str(session.id),
            'question_id': question.id,
            'answer_text': answer_text,
            'answered_at': question.answered_at.isoformat() if question.answered_at else '',
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

    def _get_or_start_generation_job(
        self,
        *,
        session: InterviewSession,
        answered_question: InterviewQuestion,
        sequence: int,
        request_hash: str,
        engine_name: str,
    ) -> tuple[InterviewQuestionGenerationJob, bool]:
        stale_seconds = getattr(settings, 'INTERVIEW_GENERATION_JOB_STALE_SECONDS', 90)
        now = timezone.now()
        with transaction.atomic():
            job = InterviewQuestionGenerationJob.objects.select_for_update().filter(
                session=session,
                sequence=sequence,
            ).first()
            if not job:
                try:
                    with transaction.atomic():
                        job = InterviewQuestionGenerationJob.objects.create(
                            session=session,
                            answered_question=answered_question,
                            sequence=sequence,
                            request_hash=request_hash,
                            engine_name=engine_name,
                            status=InterviewQuestionGenerationJob.Status.RUNNING,
                            started_at=now,
                        )
                    return job, True
                except IntegrityError:
                    job = InterviewQuestionGenerationJob.objects.select_for_update().get(
                        session=session,
                        sequence=sequence,
                    )

            if job.status == InterviewQuestionGenerationJob.Status.COMPLETED and job.generated_question_id:
                return job, False
            if job.status == InterviewQuestionGenerationJob.Status.RUNNING:
                updated_at = job.updated_at or job.started_at or job.created_at
                if updated_at and (now - updated_at).total_seconds() < stale_seconds:
                    return job, False

            job.answered_question = answered_question
            job.request_hash = request_hash
            job.engine_name = engine_name
            job.status = InterviewQuestionGenerationJob.Status.RUNNING
            job.error_message = ''
            job.partial_text = ''
            job.final_text = ''
            job.generated_question = None
            job.started_at = now
            job.completed_at = None
            job.save(update_fields=[
                'answered_question',
                'request_hash',
                'engine_name',
                'status',
                'error_message',
                'partial_text',
                'final_text',
                'generated_question',
                'started_at',
                'completed_at',
                'updated_at',
            ])
            return job, True

    def _build_answered_history(self, session: InterviewSession, current_question: InterviewQuestion | None = None) -> list:
        history = []
        for q in session.questions.filter(answered_at__isnull=False).order_by('sequence'):
            history.append({
                'sequence': q.sequence,
                'question': q.question_text,
                'answer': q.answer_text,
                'feedback': (q.ai_feedback or {}).get('feedback') if isinstance(q.ai_feedback, dict) else '',
                'evaluation': q.ai_feedback if isinstance(q.ai_feedback, dict) else {},
                'analysis_data': q.analysis_data,
                'perception_summary': self._agent().summarize_perception(q.analysis_data),
                'rag_context': q.rag_context if isinstance(q.rag_context, list) else [],
            })
        return history

    @action(detail=True, methods=['post'], url_path='submit-answer-stream')
    def submit_answer_stream(self, request, pk=None):
        session = self.get_object()
        if session.status != InterviewSession.Status.RUNNING:
            return Response({"error": "面试已结束或已取消。"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SubmitAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data['question_id']
        answer_text = serializer.validated_data['answer_text']
        analysis_data = serializer.validated_data.get('analysis_data')
        audio_artifact_id = serializer.validated_data.get('audio_artifact_id')
        asr_transcript_meta = serializer.validated_data.get('asr_transcript_meta') or {}
        async_requested = (
            'respond-async' in str(request.headers.get('Prefer', '')).lower()
            or str(request.query_params.get('async', '')).lower() in ('1', 'true', 'yes')
        )
        if async_requested:
            return run_idempotent(
                request,
                f'interview_submit_answer:{session.id}',
                lambda: self._submit_answer_async(
                    request=request,
                    session=session,
                    question_id=question_id,
                    answer_text=answer_text,
                    analysis_data=analysis_data,
                    audio_artifact_id=audio_artifact_id,
                    asr_transcript_meta=asr_transcript_meta,
                ),
            )
        try:
            with transaction.atomic():
                current_question = session.questions.select_for_update().get(id=question_id)

                if current_question.answered_at:
                    answered_count = session.questions.filter(answered_at__isnull=False).count()
                    realistic = session.experience_mode == InterviewSession.ExperienceMode.REALISTIC
                    existing_feedback = ""
                    existing_feedback_detail = None
                    if not realistic and isinstance(current_question.ai_feedback, dict):
                        existing_feedback = current_question.ai_feedback.get("feedback", "")
                        existing_feedback_detail = current_question.ai_feedback

                    termination = (session.memory_summary or {}).get('termination_decision') or {}
                    dynamically_finished = bool(
                        session.progress_mode == 'time_and_coverage'
                        and termination
                        and not termination.get('continue_interview', True)
                    )

                    response_data = {
                        "feedback": existing_feedback,
                        "feedback_detail": existing_feedback_detail,
                        "interview_finished": dynamically_finished or (
                            session.progress_mode != 'time_and_coverage' and answered_count >= session.question_count
                        ),
                        "already_answered": True,
                    }

                    next_question = session.questions.filter(sequence=answered_count + 1).first()
                    if next_question:
                        response_data["next_question"] = {
                            "id": next_question.id,
                            "question_text": next_question.question_text,
                            "sequence": next_question.sequence,
                        }
                    return Response(response_data, status=status.HTTP_200_OK)

                current_question.answer_text = answer_text
                current_question.answered_at = timezone.now()
                audio_artifact = None
                if audio_artifact_id:
                    try:
                        audio_artifact = InterviewMediaArtifact.objects.select_for_update().get(
                            id=audio_artifact_id,
                            session=session,
                            user=request.user,
                            artifact_type=InterviewMediaArtifact.ArtifactType.ANSWER_AUDIO,
                        )
                    except InterviewMediaArtifact.DoesNotExist:
                        return Response({"error": "语音记录不存在或无权使用"}, status=status.HTTP_400_BAD_REQUEST)
                    if audio_artifact.question_id and audio_artifact.question_id != current_question.id:
                        return Response({"error": "语音记录不属于当前问题"}, status=status.HTTP_400_BAD_REQUEST)
                    audio_artifact.question = current_question
                    audio_artifact.metadata = {
                        **(audio_artifact.metadata or {}),
                        'submitted_with_answer': True,
                        'asr_transcript_meta': asr_transcript_meta,
                    }
                    audio_artifact.save(update_fields=['question', 'metadata', 'updated_at'])
                    current_question.audio_url = audio_artifact.source_file.url if audio_artifact.source_file else ''
                if analysis_data and isinstance(analysis_data, list):
                    current_question.analysis_data = [
                        {'timestamp': frame.get('timestamp'), 'emotions': frame.get('emotions')}
                        for frame in analysis_data
                    ]
                current_question.save(update_fields=['answer_text', 'answered_at', 'analysis_data', 'audio_url'])
                session.last_activity_at = timezone.now()
                session.save(update_fields=['last_activity_at', 'updated_at'])
                answered_count = session.questions.filter(answered_at__isnull=False).count()
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        cache.touch(get_user_cache_key(request.user), timeout=7200)

        jd_text = (session.memory_summary or {}).get("jd_text", "")
        agent = self._agent()
        history = self._build_answered_history(session, current_question)

        resume_text = None
        if session.resume_snapshot:
            resume_text = json_resume_plain_text(session.resume_snapshot)
        elif session.resume:
            resume_text = format_resume_to_text(session.resume)

        try:
            turn_state = agent.prepare_submit_answer_turn(
                session=session,
                current_question=current_question,
                answer_text=answer_text,
                user=request.user,
                answered_count=answered_count,
                history=history,
                resume_text=resume_text,
                jd_text=jd_text,
                media_context={
                    'audio_artifact_id': str(audio_artifact_id) if audio_artifact_id else '',
                    'asr_transcript_meta': asr_transcript_meta,
                },
            )
        except RequiredRAGContextUnavailable as exc:
            return Response({
                'code': 'required_rag_unavailable',
                'message': '本轮必须使用已审批知识，但检索服务或可用证据暂不可用。',
                'reason': str(exc),
                'retryable': True,
                'paused': True,
            }, status=status.HTTP_409_CONFLICT)
        answer_evaluation = turn_state.answer_evaluation
        feedback_text = turn_state.feedback_text
        realistic = session.experience_mode == InterviewSession.ExperienceMode.REALISTIC
        public_feedback = '' if realistic else feedback_text
        public_evaluation = None if realistic else answer_evaluation

        if turn_state.interview_finished:
            response = Response({
                "feedback": public_feedback,
                "feedback_detail": public_evaluation,
                "interview_finished": True,
            }, status=status.HTTP_200_OK)
            return self._set_agent_run_header(response, getattr(turn_state, 'agent_run_id', None))

        next_sequence = answered_count + 1
        request_hash = self._generation_request_hash(session, current_question, answer_text)
        generation_job, can_generate = self._get_or_start_generation_job(
            session=session,
            answered_question=current_question,
            sequence=next_sequence,
            request_hash=request_hash,
            engine_name=getattr(settings, 'INTERVIEW_AGENT_ENGINE', 'default'),
        )
        if generation_job.status == InterviewQuestionGenerationJob.Status.COMPLETED and generation_job.generated_question:
            return Response({
                "feedback": public_feedback,
                "feedback_detail": public_evaluation,
                "interview_finished": False,
                "next_question": self._serialize_question(generation_job.generated_question),
                "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data,
                "already_generated": True,
            }, status=status.HTTP_200_OK)
        if not can_generate:
            return Response({
                "feedback": public_feedback,
                "feedback_detail": public_evaluation,
                "interview_finished": False,
                "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data,
                "error": "下一题正在生成，请稍后恢复。",
            }, status=status.HTTP_409_CONFLICT)

        def stream_response_generator():
            question_buffer = []
            last_checkpoint_length = 0
            event_sequence = 0
            run_id = getattr(turn_state, 'agent_run_id', None)
            sse_mode = 'text/event-stream' in request.headers.get('Accept', '')
            try:
                if run_id:
                    started_event = publish_agent_event(
                        thread_id=session.id,
                        run_id=run_id,
                        event_type='run.started',
                        sequence=event_sequence,
                        payload={'event': 'submit_answer_stream'},
                    )
                    if sse_mode:
                        yield started_event.to_sse()
                stream = agent.generate_question_chunks(turn_state)
                for chunk in stream:
                    question_buffer.append(chunk)
                    partial_text = "".join(question_buffer)
                    if len(partial_text) - last_checkpoint_length >= 512:
                        generation_job.partial_text = partial_text
                        generation_job.save(update_fields=['partial_text', 'updated_at'])
                        last_checkpoint_length = len(partial_text)
                    event_sequence += 1
                    delta_event = None
                    if run_id:
                        delta_event = publish_agent_event(
                            thread_id=session.id,
                            run_id=run_id,
                            event_type='question.delta',
                            sequence=event_sequence,
                            payload={'delta': chunk},
                        )
                    yield delta_event.to_sse() if sse_mode and delta_event else chunk
                full_question_text = "".join(question_buffer).strip()
                next_question = agent.finalize_generated_question(turn_state, full_question_text)
                generation_job.generated_question = next_question
                generation_job.final_text = next_question.question_text
                generation_job.partial_text = full_question_text
                generation_job.status = InterviewQuestionGenerationJob.Status.COMPLETED
                generation_job.completed_at = timezone.now()
                generation_job.save(update_fields=[
                    'generated_question',
                    'final_text',
                    'partial_text',
                    'status',
                    'completed_at',
                    'updated_at',
                ])
                serialized_question = self._serialize_question(next_question)
                event_sequence += 1
                completed_event = None
                if run_id:
                    completed_event = publish_agent_event(
                        thread_id=session.id,
                        run_id=run_id,
                        event_type='question.completed',
                        sequence=event_sequence,
                        payload={'question': serialized_question},
                    )
                if sse_mode and completed_event:
                    yield completed_event.to_sse()
                else:
                    yield '\n__FINAL_QUESTION__:' + json.dumps(
                        serialized_question,
                        ensure_ascii=False,
                        default=str,
                    )
            except GeneratorExit:
                generation_job.partial_text = "".join(question_buffer)
                generation_job.status = InterviewQuestionGenerationJob.Status.FAILED
                generation_job.error_message = 'stream_disconnected'
                generation_job.completed_at = timezone.now()
                generation_job.save(update_fields=[
                    'partial_text',
                    'status',
                    'error_message',
                    'completed_at',
                    'updated_at',
                ])
                raise
            except Exception as exc:
                if run_id:
                    event_sequence += 1
                    publish_agent_event(
                        thread_id=session.id,
                        run_id=run_id,
                        event_type='run.failed',
                        sequence=event_sequence,
                        payload={'error_code': type(exc).__name__},
                    )
                generation_job.partial_text = "".join(question_buffer)
                generation_job.status = InterviewQuestionGenerationJob.Status.FAILED
                generation_job.error_message = str(exc)[:1000]
                generation_job.completed_at = timezone.now()
                generation_job.save(update_fields=[
                    'partial_text',
                    'status',
                    'error_message',
                    'completed_at',
                    'updated_at',
                ])
                raise

        sse_mode = 'text/event-stream' in request.headers.get('Accept', '')
        response = StreamingHttpResponse(
            stream_response_generator(),
            content_type='text/event-stream; charset=utf-8' if sse_mode else 'text/plain; charset=utf-8',
        )
        if sse_mode:
            response['Cache-Control'] = 'no-cache, no-transform'
            response['X-Accel-Buffering'] = 'no'
        response['X-Feedback'] = quote(public_feedback)
        response['X-Feedback-Json'] = quote(json.dumps(public_evaluation, ensure_ascii=False))
        response['X-Generation-Job-Id'] = str(generation_job.id)
        response['Access-Control-Expose-Headers'] = 'X-Feedback, X-Feedback-Json, X-Generation-Job-Id'
        return self._set_agent_run_header(response, getattr(turn_state, 'agent_run_id', None))

    def _submit_answer_async(
        self,
        *,
        request,
        session,
        question_id,
        answer_text,
        analysis_data,
        audio_artifact_id,
        asr_transcript_meta,
    ):
        idempotency_key = str(request.headers.get('Idempotency-Key') or '').strip()
        if not idempotency_key:
            return Response({
                'code': 'idempotency_key_required',
                'message': '异步回答提交必须提供 Idempotency-Key。',
                'retryable': False,
            }, status=status.HTTP_400_BAD_REQUEST)
        if len(idempotency_key) > 128:
            return Response({
                'code': 'idempotency_key_too_long',
                'message': 'Idempotency-Key 不能超过 128 个字符。',
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic(), short_lock_timeout():
                User.objects.select_for_update().get(id=request.user.id)
                locked_session = InterviewSession.objects.select_for_update().get(
                    id=session.id,
                    user=request.user,
                )
                if locked_session.status != InterviewSession.Status.RUNNING:
                    return Response({'code': 'interview_not_running', 'message': '面试已结束或已取消。'}, status=409)
                question = InterviewQuestion.objects.select_for_update().get(
                    id=question_id,
                    session=locked_session,
                )
                if question.answered_at:
                    if question.answer_text != answer_text:
                        return Response({
                            'code': 'answer_conflict',
                            'message': '该问题已提交过不同回答。',
                            'retryable': False,
                        }, status=409)
                    execution = locked_session.agent_executions.filter(
                        trigger_question=question,
                    ).order_by('-created_at').first()
                    if execution:
                        response = Response({
                            'run_id': str(execution.run_id),
                            'status': execution.status,
                            'events_url': f'/api/v1/interviews/{locked_session.id}/agent-executions/{execution.run_id}/events/',
                            'resume_url': f'/api/v1/interviews/{locked_session.id}/resume-state/',
                            'already_answered': True,
                        }, status=status.HTTP_202_ACCEPTED)
                        response['X-Agent-Run-Id'] = str(execution.run_id)
                        response['X-Idempotent-Replay'] = 'true'
                        return response
                    return Response({
                        'code': 'answer_persisted_without_execution',
                        'message': '回答已保存但生成任务缺失，请重试恢复。',
                        'retryable': True,
                    }, status=409)

                question.answer_text = answer_text
                question.answered_at = timezone.now()
                media_context = {
                    'audio_artifact_id': str(audio_artifact_id) if audio_artifact_id else '',
                    'asr_transcript_meta': asr_transcript_meta,
                }
                if audio_artifact_id:
                    audio_artifact = InterviewMediaArtifact.objects.select_for_update().get(
                        id=audio_artifact_id,
                        session=locked_session,
                        user=request.user,
                        artifact_type=InterviewMediaArtifact.ArtifactType.ANSWER_AUDIO,
                    )
                    if audio_artifact.question_id and audio_artifact.question_id != question.id:
                        return Response({'code': 'audio_question_conflict', 'message': '语音记录不属于当前问题。'}, status=409)
                    audio_artifact.question = question
                    audio_artifact.metadata = {
                        **(audio_artifact.metadata or {}),
                        'submitted_with_answer': True,
                        'asr_transcript_meta': asr_transcript_meta,
                    }
                    audio_artifact.save(update_fields=['question', 'metadata', 'updated_at'])
                    question.audio_url = audio_artifact.source_file.url if audio_artifact.source_file else ''
                if analysis_data and isinstance(analysis_data, list):
                    question.analysis_data = [
                        {'timestamp': frame.get('timestamp'), 'emotions': frame.get('emotions')}
                        for frame in analysis_data
                    ]
                question.save(update_fields=['answer_text', 'answered_at', 'analysis_data', 'audio_url'])
                locked_session.last_activity_at = timezone.now()
                locked_session.save(update_fields=['last_activity_at', 'updated_at'])
                answered_count = locked_session.questions.filter(answered_at__isnull=False).count()
                execution, generation_job, _ = create_answer_execution(
                    session=locked_session,
                    question=question,
                    answer_text=answer_text,
                    client_idempotency_key=idempotency_key,
                    answered_count=answered_count,
                    media_context=media_context,
                )

                def enqueue_dispatch():
                    try:
                        from .tasks import publish_pending_agent_dispatches
                        publish_pending_agent_dispatches.apply_async(queue='notifications')
                    except Exception:
                        pass

                transaction.on_commit(enqueue_dispatch)
        except InterviewQuestion.DoesNotExist:
            return Response({'code': 'question_not_found', 'message': '问题不存在。'}, status=404)
        except InterviewMediaArtifact.DoesNotExist:
            return Response({'code': 'audio_not_found', 'message': '语音记录不存在或无权使用。'}, status=404)
        except Exception as exc:
            if type(exc).__name__ in ('OperationalError', 'LockNotAvailable'):
                return Response({
                    'code': 'operation_busy',
                    'message': '当前面试正在处理另一个操作，请稍后重试。',
                    'retryable': True,
                    'retry_after_ms': 750,
                }, status=409)
            raise

        response = Response({
            'run_id': str(execution.run_id),
            'status': execution.status,
            'events_url': f'/api/v1/interviews/{session.id}/agent-executions/{execution.run_id}/events/',
            'resume_url': f'/api/v1/interviews/{session.id}/resume-state/',
            'generation_job': InterviewQuestionGenerationJobSerializer(generation_job).data,
        }, status=status.HTTP_202_ACCEPTED)
        response['X-Agent-Run-Id'] = str(execution.run_id)
        response['Access-Control-Expose-Headers'] = 'X-Agent-Run-Id'
        return response

    def _complete_recovered_execution(self, session, answered_question, result_question=None):
        with transaction.atomic():
            execution = session.agent_executions.select_for_update().filter(
                trigger_question=answered_question,
            ).order_by('-created_at').first()
            if not execution:
                return
            execution.status = InterviewAgentExecution.Status.COMPLETED
            execution.result_question = result_question
            execution.completed_at = timezone.now()
            execution.error_code = ''
            execution.version += 1
            execution.save(update_fields=[
                'status', 'result_question', 'completed_at', 'error_code', 'version', 'updated_at',
            ])

    @action(detail=True, methods=['post'], url_path='regenerate-next-question')
    def regenerate_next_question(self, request, pk=None):
        session = self.get_object()
        if session.status != InterviewSession.Status.RUNNING:
            return Response({"error": "面试已结束或已取消。"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RegenerateNextQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data['question_id']

        try:
            answered_question = session.questions.get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        if not answered_question.answered_at:
            return Response({"error": "当前问题还没有提交回答，无法恢复下一题。"}, status=status.HTTP_400_BAD_REQUEST)

        answered_count = session.questions.filter(answered_at__isnull=False).count()
        public_feedback_detail = (
            answered_question.ai_feedback
            if session.experience_mode == InterviewSession.ExperienceMode.COACHING and isinstance(answered_question.ai_feedback, dict)
            else None
        )
        termination = (session.memory_summary or {}).get('termination_decision') or {}
        dynamically_finished = bool(
            session.progress_mode == 'time_and_coverage'
            and termination
            and not termination.get('continue_interview', True)
        )
        if dynamically_finished or (session.progress_mode != 'time_and_coverage' and answered_count >= session.question_count):
            return Response({
                "interview_finished": True,
                "feedback_detail": public_feedback_detail,
            }, status=status.HTTP_200_OK)

        next_sequence = answered_count + 1
        existing_next_question = session.questions.filter(sequence=next_sequence).first()
        if existing_next_question:
            generation_job = session.question_generation_jobs.filter(sequence=next_sequence).first()
            if generation_job and generation_job.status != InterviewQuestionGenerationJob.Status.COMPLETED:
                generation_job.generated_question = existing_next_question
                generation_job.final_text = existing_next_question.question_text
                generation_job.status = InterviewQuestionGenerationJob.Status.COMPLETED
                generation_job.completed_at = generation_job.completed_at or timezone.now()
                generation_job.save(update_fields=['generated_question', 'final_text', 'status', 'completed_at', 'updated_at'])
            self._complete_recovered_execution(session, answered_question, existing_next_question)
            return Response({
                "next_question": self._serialize_question(existing_next_question),
                "already_exists": True,
                "feedback_detail": public_feedback_detail,
                "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data if generation_job else None,
            }, status=status.HTTP_200_OK)

        request_hash = self._generation_request_hash(session, answered_question, answered_question.answer_text)
        generation_job, can_generate = self._get_or_start_generation_job(
            session=session,
            answered_question=answered_question,
            sequence=next_sequence,
            request_hash=request_hash,
            engine_name=getattr(settings, 'INTERVIEW_AGENT_ENGINE', 'default'),
        )
        if generation_job.status == InterviewQuestionGenerationJob.Status.COMPLETED and generation_job.generated_question:
            self._complete_recovered_execution(session, answered_question, generation_job.generated_question)
            return Response({
                "next_question": self._serialize_question(generation_job.generated_question),
                "already_exists": True,
                "feedback_detail": public_feedback_detail,
                "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data,
            }, status=status.HTTP_200_OK)
        if not can_generate:
            return Response({
                "error": "下一题正在生成，请稍后重试。",
                "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data,
                "feedback_detail": public_feedback_detail,
            }, status=status.HTTP_409_CONFLICT)

        resume_text = format_resume_to_text(session.resume) if session.resume else None
        jd_text = (session.memory_summary or {}).get("jd_text", "")
        history = self._build_answered_history(session, answered_question)
        last_evaluation = answered_question.ai_feedback if isinstance(answered_question.ai_feedback, dict) else {}
        agent = self._agent()
        try:
            turn_state = agent.prepare_regenerate_question_turn(
                session=session,
                answered_question=answered_question,
                user=request.user,
                answered_count=answered_count,
                history=history,
                resume_text=resume_text,
                jd_text=jd_text,
            )
        except RequiredRAGContextUnavailable as exc:
            return Response({
                'code': 'required_rag_unavailable',
                'message': '本轮必须使用已审批知识，但检索服务或可用证据暂不可用。',
                'reason': str(exc),
                'retryable': True,
                'paused': True,
            }, status=status.HTTP_409_CONFLICT)
        if turn_state.interview_finished:
            generation_job.status = InterviewQuestionGenerationJob.Status.COMPLETED
            generation_job.completed_at = timezone.now()
            generation_job.save(update_fields=['status', 'completed_at', 'updated_at'])
            response = Response({
                'interview_finished': True,
                'feedback_detail': public_feedback_detail,
                'generation_job': InterviewQuestionGenerationJobSerializer(generation_job).data,
            }, status=status.HTTP_200_OK)
            return self._set_agent_run_header(response, getattr(turn_state, 'agent_run_id', None))
        question_text = "".join(agent.generate_question_chunks(turn_state)).strip()
        try:
            next_question = agent.finalize_generated_question(turn_state, question_text)
            generation_job.generated_question = next_question
            generation_job.final_text = next_question.question_text
            generation_job.partial_text = question_text
            generation_job.status = InterviewQuestionGenerationJob.Status.COMPLETED
            generation_job.completed_at = timezone.now()
            generation_job.save(update_fields=[
                'generated_question',
                'final_text',
                'partial_text',
                'status',
                'completed_at',
                'updated_at',
            ])
        except Exception as exc:
            generation_job.partial_text = question_text
            generation_job.status = InterviewQuestionGenerationJob.Status.FAILED
            generation_job.error_message = str(exc)[:1000]
            generation_job.completed_at = timezone.now()
            generation_job.save(update_fields=[
                'partial_text',
                'status',
                'error_message',
                'completed_at',
                'updated_at',
            ])
            raise

        response = Response({
            "next_question": self._serialize_question(next_question),
            "already_exists": False,
            "feedback_detail": last_evaluation if session.experience_mode == InterviewSession.ExperienceMode.COACHING else None,
            "generation_job": InterviewQuestionGenerationJobSerializer(generation_job).data,
        }, status=status.HTTP_200_OK)
        self._complete_recovered_execution(session, answered_question, next_question)
        return self._set_agent_run_header(response, getattr(turn_state, 'agent_run_id', None))

    @action(detail=True, methods=['post'], url_path='finish')
    def finish_interview(self, request, pk=None):
        session = self.get_object()
        cache_key = get_user_cache_key(request.user)

        if session.report:
            return Response(session.report, status=status.HTTP_200_OK)

        if session.status == InterviewSession.Status.CANCELED:
            return Response({"error": "已取消的面试无法生成报告"}, status=status.HTTP_400_BAD_REQUEST)

        history = []
        answered_questions = session.questions.filter(answered_at__isnull=False).order_by('sequence')
        for q in answered_questions:
            history.append({
                'sequence': q.sequence,
                'question': q.question_text,
                'answer': q.answer_text,
                'analysis_data': q.analysis_data,
                'ai_feedback': q.ai_feedback if isinstance(q.ai_feedback, dict) else {},
                'evaluation': q.ai_feedback if isinstance(q.ai_feedback, dict) else {},
                'rag_context': q.rag_context if isinstance(q.rag_context, list) else [],
            })
        if not history:
            return Response({"error": "没有有效的问答记录，无法生成报告"}, status=status.HTTP_400_BAD_REQUEST)

        resume_text = None
        if session.resume:
            resume_text = format_resume_to_text(session.resume)

        trace_summary = [
            {
                'event': trace.event,
                'stage': trace.stage,
                'question': trace.generated_question,
                'rag_sources': [
                    {
                        'title': item.get('title'),
                        'visibility': item.get('visibility'),
                        'ability_tags': item.get('ability_tags'),
                    }
                    for item in (trace.rag_context or [])[:3]
                    if isinstance(item, dict)
                ],
                'fallback_reason': trace.fallback_reason,
            }
            for trace in session.agent_traces.order_by('created_at')[:20]
        ]
        report_memory = {
            **(session.memory_summary or {}),
            'agent_trace_summary': trace_summary,
        }

        report_agent = self._agent()
        report_kwargs = dict(
            job_position=session.job_position,
            interview_history=history,
            user=request.user,
            resume_text=resume_text,
            memory_summary=report_memory,
            agent_config_snapshot=session.agent_config_snapshot,
            context_envelope=assemble_generation_context(
                session=session,
                history=history,
                rag_context=[
                    item
                    for turn in history
                    for item in (turn.get('rag_context') or [])
                    if isinstance(item, dict)
                ],
                memory_events=[],
                media_context={},
                task_context={
                    'task': 'final_report',
                    'agent_trace_summary': trace_summary,
                },
                resume_text=resume_text or '',
                jd_text=session.jd_snapshot or '',
            ),
        )
        if getattr(report_agent, 'engine_name', '').startswith('composite_v'):
            report_kwargs['session'] = session
        report_data = report_agent.generate_report(**report_kwargs)

        if "error" in report_data:
            return Response(report_data, status=status.HTTP_502_BAD_GATEWAY)

        score_summary = summarize_report_scores(history, session.session_plan)
        if score_summary.get('overall_score'):
            report_data['overall_score'] = score_summary['overall_score']
        if score_summary.get('ability_scores'):
            report_data['ability_scores'] = score_summary['ability_scores']
        report_data['coverage_summary'] = session.coverage_summary
        report_data['template_snapshot'] = session.template_snapshot
        report_data['evaluation_version'] = {
            'mode': 'rule_ai_dual',
            'rule_weight': 0.7,
            'ai_weight': 0.3,
        }

        session.report = report_data
        session.status = InterviewSession.Status.FINISHED
        session.current_stage = InterviewSession.InterviewStage.WRAP_UP
        session.finished_at = timezone.now()
        
        if session.recording_enabled:
            finish_serializer = FinishInterviewSerializer(data=request.data)
            if finish_serializer.is_valid():
                video_upload_id = finish_serializer.validated_data.get('video_upload_id')
                recording_data = finish_serializer.validated_data.get('recording_data')
                print(f"[录像] finish接口收到数据 - video_upload_id: {video_upload_id}, recording_data: {recording_data}")
                
                if video_upload_id:
                    try:
                        from video_uploads.models import FileUploadTask
                        upload_task = FileUploadTask.objects.get(id=video_upload_id, user=request.user)
                        session.video_upload_task = upload_task
                        print(f"[录像] 成功关联video_upload_task: {upload_task.id}")
                    except FileUploadTask.DoesNotExist:
                        print(f"[录像] FileUploadTask不存在: {video_upload_id}")
                    except Exception as e:
                        print(f"[录像] 关联video_upload_task失败: {e}")
                elif recording_data:
                    from video_uploads.models import FileUploadTask
                    upload_task = FileUploadTask.objects.create(
                        user=request.user,
                        file_identifier=recording_data.get('file_identifier'),
                        file_name=f"interview_{session.id}.mp4",
                        file_size=recording_data.get('file_size'),
                        total_chunks=recording_data.get('total_chunks'),
                        chunk_size=recording_data.get('chunk_size', 5 * 1024 * 1024),
                        status=FileUploadTask.Status.UPLOADING
                    )
                    session.video_upload_task = upload_task
        
        with transaction.atomic():
            session.save()
            from careers.services import record_timeline_event
            from core.events import enqueue_integration_event
            record_timeline_event(
                user=request.user,
                event_type='interview.completed',
                title=f'完成专项面试：{session.job_position}',
                source_type='InterviewSession',
                source_id=session.pk,
                metadata={'job_target_id': session.job_target_id},
                occurred_at=session.finished_at,
            )
            enqueue_integration_event(
                event_type='interview.completed',
                producer='interviews',
                aggregate_type='InterviewSession',
                aggregate_id=session.pk,
                actor_id=request.user.pk,
                payload={
                    'interview_session_id': str(session.pk),
                    'job_target_id': session.job_target_id,
                    'status': session.status,
                },
            )
        cache.delete(cache_key)
        
        response_data = report_data.copy()
        response_data['recording_enabled'] = session.recording_enabled
        if session.video_upload_task:
            response_data['video_upload_task_id'] = str(session.video_upload_task.id)
        
        return Response(response_data, status=status.HTTP_200_OK)

        # --- [核心新增] 新增一个 action 用于获取 AI 参考答案 ---

    @action(detail=False, methods=['get'], url_path=r'questions/(?P<question_pk>\d+)/reference-answer')
    def get_reference_answer(self, request, question_pk=None):
        try:
            question = InterviewQuestion.objects.get(pk=question_pk, session__user=request.user)
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在或您没有权限访问"}, status=status.HTTP_404_NOT_FOUND)

        prompt_version = getattr(settings, 'AGENT_PROMPT_VERSION', 'interview-agent-v1')
        ai_setting = AISetting.objects.filter(user=request.user).select_related('chat_model', 'ai_model').first()
        selected_model = (ai_setting.chat_model if ai_setting else None) or (ai_setting.ai_model if ai_setting else None)
        model_alias = selected_model.name if selected_model else 'interview.reference.default'
        source_hash = hashlib.sha256(
            f'{question.id}:{question.question_text}:{question.session.job_position}'.encode('utf-8')
        ).hexdigest()
        cache_key = f'ref_answer:{request.user.id}:{question_pk}:{prompt_version}:{model_alias}'
        snapshot, created = InterviewReferenceAnswer.objects.get_or_create(
            question=question,
            user=request.user,
            prompt_version=prompt_version,
            model_alias=model_alias,
            defaults={'source_hash': source_hash},
        )
        if snapshot.status == InterviewReferenceAnswer.Status.COMPLETED and snapshot.answer:
            from core.cache_policy import set_policy_value
            set_policy_value(cache_key, snapshot.answer, 'reference_answer')
            response = Response({'answer': snapshot.answer, 'snapshot_id': str(snapshot.id)})
            response['X-Cache-State'] = 'postgresql'
            return response
        if not created and snapshot.status == InterviewReferenceAnswer.Status.PENDING:
            age = (timezone.now() - snapshot.updated_at).total_seconds()
            if age < 120:
                return Response({
                    'code': 'reference_answer_processing',
                    'message': '参考答案正在生成。',
                    'retryable': True,
                    'retry_after_ms': 1000,
                    'operation_id': str(snapshot.id),
                }, status=status.HTTP_202_ACCEPTED)
        InterviewReferenceAnswer.objects.filter(id=snapshot.id).update(
            status=InterviewReferenceAnswer.Status.PENDING,
            error_code='',
            source_hash=source_hash,
            updated_at=timezone.now(),
        )

        # 获取简历文本
        resume_text = None
        if question.session.resume:
            resume_text = format_resume_to_text(question.session.resume)

        # 调用新的 AI 服务
        try:
            reference_answer = generate_reference_answer_for_question(
                job_position=question.session.job_position,
                question=question.question_text,
                user=request.user,
                resume_text=resume_text
            )
        except Exception as exc:
            InterviewReferenceAnswer.objects.filter(id=snapshot.id).update(
                status=InterviewReferenceAnswer.Status.FAILED,
                error_code=type(exc).__name__[:120],
                updated_at=timezone.now(),
            )
            return Response({
                'code': 'reference_answer_unavailable',
                'message': '参考答案生成失败，请稍后重试。',
                'retryable': True,
                'operation_id': str(snapshot.id),
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not reference_answer:
            InterviewReferenceAnswer.objects.filter(id=snapshot.id).update(
                status=InterviewReferenceAnswer.Status.FAILED,
                error_code='empty_model_response',
                updated_at=timezone.now(),
            )
            return Response({
                'code': 'reference_answer_unavailable',
                'message': '参考答案生成失败，请稍后重试。',
                'retryable': True,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        InterviewReferenceAnswer.objects.filter(id=snapshot.id).update(
            answer=reference_answer,
            status=InterviewReferenceAnswer.Status.COMPLETED,
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        from core.cache_policy import set_policy_value
        set_policy_value(cache_key, reference_answer, 'reference_answer')

        return Response({'answer': reference_answer, 'snapshot_id': str(snapshot.id)}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='recording')
    def get_recording(self, request, pk=None):
        session = self.get_object()
        
        if not session.recording_enabled:
            return Response({
                'has_recording': False,
                'recording_enabled': False,
                'status': None,
                'progress': 0,
                'video_url': None,
                'error_message': None,
                'playback_source': None,
                'fallback_available': False,
                'transcode_status': None,
                'transcode_progress': 0,
                'transcode_error_message': None,
            }, status=status.HTTP_200_OK)
        
        if not session.video_upload_task:
            return Response({
                'has_recording': True,
                'recording_enabled': True,
                'status': 'pending',
                'progress': 0,
                'video_url': None,
                'error_message': None,
                'playback_source': None,
                'fallback_available': False,
                'transcode_status': None,
                'transcode_progress': 0,
                'transcode_error_message': None,
            }, status=status.HTTP_200_OK)
        
        upload_task = session.video_upload_task
        
        status_map = {
            'pending': 'pending',
            'uploading': 'uploading', 
            'merging': 'transcoding',
            'merged': 'completed',
            'completed': 'completed',
            'failed': 'failed'
        }
        
        video_status = status_map.get(upload_task.status, 'pending')
        video_url = None
        playback_source = None
        fallback_available = False
        transcode_status = None
        transcode_progress = 0
        transcode_error_message = None
        progress = 100 if upload_task.status in ['merged', 'completed'] else (getattr(upload_task, 'progress_percent', 0) or 0)
        
        error_message = None

        if hasattr(upload_task, 'transcode_task') and upload_task.transcode_task:
            transcode_task = upload_task.transcode_task
            transcode_status = transcode_task.status
            transcode_progress = transcode_task.progress or 0
            if transcode_task.status == 'pending':
                video_status = 'transcoding'
                progress = 0
                if upload_task.merged_file_path:
                    try:
                        from video_uploads.tasks import transcode_video_task
                        if not transcode_task.original_file:
                            transcode_task.original_file = upload_task.merged_file_path
                        transcode_task.status = 'processing'
                        transcode_task.started_at = timezone.now()
                        transcode_task.save(update_fields=['original_file', 'status', 'started_at'])
                        transcode_video_task.delay(str(transcode_task.id))
                    except Exception as e:
                        error_message = f'转码任务调度失败: {str(e)[:300]}'
                        transcode_error_message = error_message
            elif transcode_task.status == 'processing':
                video_status = 'transcoding'
                progress = transcode_task.progress or 0
                transcode_progress = progress
            elif transcode_task.status == 'completed':
                video_status = 'completed'
                progress = 100
                transcode_progress = 100
                if transcode_task.transcoded_file:
                    video_url = request.build_absolute_uri(
                        transcode_task.transcoded_file.replace('\\', '/').replace('media/', '/media/')
                    )
                    playback_source = 'transcoded'
            elif transcode_task.status == 'failed':
                video_status = 'failed'
                transcode_error_message = transcode_task.error_message or '视频处理失败'
                error_message = transcode_error_message
        
        if not video_url and upload_task.merged_file_path:
            import os
            if os.path.exists(upload_task.merged_file_path):
                video_url = request.build_absolute_uri(
                    upload_task.merged_file_path.replace('\\', '/').replace('media/', '/media/')
                )
                playback_source = 'original'
                fallback_available = True
                if video_status in ['transcoding', 'pending']:
                    error_message = '已先加载原始录像，后台转码完成后会自动切换为压缩版本。'
                elif video_status == 'failed':
                    error_message = f"{error_message or '转码失败'}，已切换为原始录像播放。"
                video_status = 'completed'
                progress = 100
        
        response_data = {
            'has_recording': True,
            'recording_enabled': True,
            'status': video_status,
            'progress': progress,
            'video_url': video_url,
            'error_message': error_message,
            'playback_source': playback_source,
            'fallback_available': fallback_available,
            'transcode_status': transcode_status,
            'transcode_progress': transcode_progress,
            'transcode_error_message': transcode_error_message,
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


class PolishDescriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        original_html = request.data.get('html_content')
        job_position = request.data.get('job_position')

        if not original_html:
            return Response({'error': '缺少 html_content 字段'}, status=status.HTTP_400_BAD_REQUEST)

        polished_html = polish_description_by_ai(
            original_html=original_html,
            user=request.user,
            job_position=job_position
        )

        return Response({'polished_html': polished_html}, status=status.HTTP_200_OK)


class ResumeAnalysisView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from resumes.legacy import legacy_job_match_response

        resume_id = request.data.get('resume_id')
        resume_version_id = request.data.get('resume_version_id')
        job_target_id = request.data.get('job_target_id')
        jd_text = str(request.data.get('jd_text') or '').strip()

        if not resume_id and not resume_version_id:
            return Response({
                'error': '必须提供 resume_version_id 或 resume_id',
                'code': 'resume_required',
            }, status=status.HTTP_400_BAD_REQUEST)

        resume_version = None
        resume_instance = None
        if resume_version_id:
            try:
                resume_version = ResumeVersion.objects.select_related('resume').get(
                    id=resume_version_id, resume__user=request.user
                )
                resume_instance = resume_version.resume
            except ResumeVersion.DoesNotExist:
                return Response({'error': '简历版本不存在', 'code': 'resume_version_not_found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            try:
                resume_instance = Resume.objects.get(id=resume_id, user=request.user)
            except Resume.DoesNotExist:
                return Response({'error': '简历不存在', 'code': 'resume_not_found'}, status=status.HTTP_404_NOT_FOUND)
            import_job = resume_instance.import_jobs.order_by('-created_at').first()
            if import_job and import_job.status in {
                ResumeImportJob.Status.PENDING,
                ResumeImportJob.Status.PROCESSING,
                ResumeImportJob.Status.REVIEW_REQUIRED,
            }:
                return Response({
                    'error': '简历导入尚未完成，请完成解析确认后再分析',
                    'code': 'resume_import_not_ready',
                    'import_job_id': import_job.id,
                    'import_status': import_job.status,
                }, status=status.HTTP_409_CONFLICT)
            resume_version = resume_instance.current_version

        job_target = None
        if job_target_id:
            try:
                job_target = JobTarget.objects.get(id=job_target_id, user=request.user)
            except JobTarget.DoesNotExist:
                return Response({'error': '目标岗位不存在', 'code': 'job_target_not_found'}, status=status.HTTP_404_NOT_FOUND)
            jd_text = str(job_target.jd_text or '').strip()
        if not resume_version:
            from resumes.versioning import ensure_resume_version
            resume_version = ensure_resume_version(resume_instance, request.user)
        return legacy_job_match_response(
            request,
            resume_version=resume_version,
            jd_text=jd_text,
            job_target=job_target,
            scope=f'legacy.interviews.analyze_resume:{resume_version.pk}',
        )


class GenerateResumeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        return Response({
            'code': 'legacy_resume_generation_retired',
            'message': '旧 AI 整包生成接口已停用。请在 Resume Studio 中基于已确认职业事实生成候选建议。',
            'migration_url': '/dashboard/resumes',
            'replacement_task_key': 'resume.from_career_facts',
        }, status=status.HTTP_410_GONE)
