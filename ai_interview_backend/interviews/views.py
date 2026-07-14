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
from rest_framework.views import APIView
from resumes.models import Resume, ResumeImportJob, ResumeVersion
from resumes.json_resume import json_resume_plain_text
from careers.models import JobTarget
from system.models import AISetting
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
    InterviewAgentMemoryEvent,
    InterviewAgentRun,
    InterviewAgentToolCall,
    InterviewAgentTrace,
    InterviewCalibrationCase,
    InterviewMediaArtifact,
    InterviewQuestion,
    InterviewQuestionGenerationJob,
    InterviewRubric,
    InterviewSession,
    InterviewTemplate,
)
from .serializers import (
    InterviewSessionSerializer,
    StartInterviewSerializer,
    SubmitAnswerSerializer,
    FinishInterviewSerializer,
    EvaluationDatasetSerializer,
    EvaluationRunSerializer,
    InterviewAgentMemoryEventSerializer,
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
    analyze_resume_against_jd,
    polish_description_by_ai,
    generate_resume_by_ai,
    generate_reference_answer_for_question,
)
from .agent import get_interview_agent_engine
from .speech_services import synthesize_question_tts
from urllib.parse import quote
from reports.models import ResumeAnalysisReport
from reports.serializers import ResumeAnalysisReportSerializer

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

    @action(detail=False, methods=['post'], url_path='start')
    def start_interview(self, request):
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
        serializer = StartInterviewSerializer(data=request.data)
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
            jd_text=jd_text
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
        if session.resume:
            resume_text = format_resume_to_text(session.resume)

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
            try:
                stream = agent.generate_question_chunks(turn_state)
                for chunk in stream:
                    question_buffer.append(chunk)
                    partial_text = "".join(question_buffer)
                    if len(partial_text) - last_checkpoint_length >= 512:
                        generation_job.partial_text = partial_text
                        generation_job.save(update_fields=['partial_text', 'updated_at'])
                        last_checkpoint_length = len(partial_text)
                    yield chunk
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
                yield '\n__FINAL_QUESTION__:' + json.dumps(
                    self._serialize_question(next_question),
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

        response = StreamingHttpResponse(stream_response_generator(), content_type='text/plain; charset=utf-8')
        response['X-Feedback'] = quote(public_feedback)
        response['X-Feedback-Json'] = quote(json.dumps(public_evaluation, ensure_ascii=False))
        response['X-Generation-Job-Id'] = str(generation_job.id)
        response['Access-Control-Expose-Headers'] = 'X-Feedback, X-Feedback-Json, X-Generation-Job-Id'
        return self._set_agent_run_header(response, getattr(turn_state, 'agent_run_id', None))

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
        turn_state = agent.prepare_regenerate_question_turn(
            session=session,
            answered_question=answered_question,
            user=request.user,
            answered_count=answered_count,
            history=history,
            resume_text=resume_text,
            jd_text=jd_text,
        )
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
            memory_summary=report_memory
        )
        if getattr(report_agent, 'engine_name', '') == 'composite_v2':
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
        
        session.save()
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

        # 尝试从缓存获取
        cache_key = f"ref_answer_{question_pk}"
        cached_answer = cache.get(cache_key)
        if cached_answer:
            return Response({"answer": cached_answer}, status=status.HTTP_200_OK)

        # 获取简历文本
        resume_text = None
        if question.session.resume:
            resume_text = format_resume_to_text(question.session.resume)

        # 调用新的 AI 服务
        reference_answer = generate_reference_answer_for_question(
            job_position=question.session.job_position,
            question=question.question_text,
            user=request.user,
            resume_text=resume_text
        )

        # 存入缓存，有效期 1 小时
        cache.set(cache_key, reference_answer, timeout=3600)

        return Response({"answer": reference_answer}, status=status.HTTP_200_OK)

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
        if not jd_text:
            return Response({
                'error': '请提供真实岗位 JD 或选择包含 JD 的目标岗位',
                'code': 'jd_required',
            }, status=status.HTTP_400_BAD_REQUEST)

        if resume_version:
            resume_snapshot = resume_version.resume_json or {}
            resume_text = json_resume_plain_text(resume_snapshot)
        else:
            resume_snapshot = {}
            resume_text = format_resume_to_text(resume_instance)
        if not resume_text.strip():
            return Response({
                'error': '简历没有可分析的已确认内容',
                'code': 'resume_content_empty',
            }, status=status.HTTP_409_CONFLICT)

        # 1. 调用AI服务
        analysis_report_data = analyze_resume_against_jd(
            resume_text=resume_text,
            jd_text=jd_text,
            user=request.user
        )

        if "error" in analysis_report_data:
            return Response(analysis_report_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            ai_setting = AISetting.objects.select_related('chat_model').filter(user=request.user).first()
            model_snapshot = {
                'chat_model_id': ai_setting.chat_model_id if ai_setting else None,
                'chat_model_slug': ai_setting.chat_model.model_slug if ai_setting and ai_setting.chat_model else '',
            }
            new_report = ResumeAnalysisReport.objects.create(
                user=request.user,
                resume=resume_instance,
                resume_version=resume_version,
                job_target=job_target,
                resume_snapshot=resume_snapshot,
                jd_text=jd_text,
                model_config_snapshot=model_snapshot,
                evidence_sources=[{
                    'type': 'resume_version' if resume_version else 'legacy_resume',
                    'resume_id': resume_instance.id,
                    'resume_version_id': resume_version.id if resume_version else None,
                }, {
                    'type': 'job_target' if job_target else 'provided_jd',
                    'job_target_id': job_target.id if job_target else None,
                }],
                report_data=analysis_report_data,
                overall_score=analysis_report_data.get('overall_score', 0)
            )
        except Exception as e:
            return Response({'error': f'保存分析报告失败: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = ResumeAnalysisReportSerializer(new_report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GenerateResumeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        position = request.data.get('position')
        experience_years = request.data.get('experience_years')
        keywords = request.data.get('keywords', '')

        if not all([name, position, experience_years]):
            return Response({'error': '姓名、岗位和工作年限为必填项'}, status=status.HTTP_400_BAD_REQUEST)

        resume_json = generate_resume_by_ai(
            name, position, experience_years, keywords, request.user
        )

        if 'error' in resume_json:
            return Response(resume_json, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(resume_json, status=status.HTTP_200_OK)
