# ai_interview_backend/interviews/views.py

from django.utils import timezone
from django.http import StreamingHttpResponse
from django.core.cache import cache
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from resumes.models import Resume
from .models import InterviewSession, InterviewQuestion
from .serializers import InterviewSessionSerializer, StartInterviewSerializer, SubmitAnswerSerializer
from .ai_services import (
    generate_first_question,
    analyze_answer,
    generate_next_question_stream,
    generate_final_report,
    analyze_resume_against_jd,
    polish_description_by_ai, generate_resume_by_ai
)
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


class InterviewSessionViewSet(viewsets.ModelViewSet):
    queryset = InterviewSession.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InterviewSessionSerializer

    def get_queryset(self):
        return InterviewSession.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='check-unfinished')
    def check_unfinished(self, request):
        cache_key = get_user_cache_key(request.user)
        session_id = cache.get(cache_key)
        if session_id:
            try:
                session = InterviewSession.objects.get(id=session_id, user=request.user,
                                                       status=InterviewSession.Status.RUNNING)
                return Response(
                    {"has_unfinished": True, "session_id": session.id, "job_position": session.job_position, },
                    status=status.HTTP_200_OK)
            except InterviewSession.DoesNotExist:
                cache.delete(cache_key)
        return Response({"has_unfinished": False}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='abandon-unfinished')
    def abandon_unfinished(self, request):
        cache_key = get_user_cache_key(request.user)
        session_id = cache.get(cache_key)
        if session_id:
            try:
                session = InterviewSession.objects.get(id=session_id, user=request.user)
                session.status = InterviewSession.Status.CANCELED
                session.save()
                cache.delete(cache_key)
                return Response({"message": "面试已放弃"}, status=status.HTTP_200_OK)
            except InterviewSession.DoesNotExist:
                cache.delete(cache_key)
        return Response({"message": "没有需要放弃的面试"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='start')
    def start_interview(self, request):
        force_start = request.query_params.get('force', 'false').lower() == 'true'
        cache_key = get_user_cache_key(request.user)
        existing_session_id = cache.get(cache_key)
        if existing_session_id and not force_start:
            return Response({"error": "您有正在进行的面试..."}, status=status.HTTP_409_CONFLICT)
        if existing_session_id and force_start:
            try:
                old_session = InterviewSession.objects.get(id=existing_session_id, user=request.user)
                old_session.status = InterviewSession.Status.CANCELED
                old_session.save()
            except InterviewSession.DoesNotExist:
                pass
            cache.delete(cache_key)

        serializer = StartInterviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job_position = serializer.validated_data['job_position']
        resume_id = serializer.validated_data.get('resume_id')
        question_count = serializer.validated_data.get('question_count')

        resume_text = ""
        resume_instance = None
        if resume_id:
            try:
                resume_instance = Resume.objects.get(id=resume_id, user=request.user)
                resume_text = format_resume_to_text(resume_instance)
                print("已为面试提取简历文本。")
            except Resume.DoesNotExist:
                return Response({"error": "简历不存在"}, status=status.HTTP_404_NOT_FOUND)

        session = InterviewSession.objects.create(
            user=request.user, job_position=job_position, resume=resume_instance,
            question_count=question_count, status=InterviewSession.Status.RUNNING, started_at=timezone.now()
        )
        first_question_text = generate_first_question(job_position, request.user, resume_text)
        InterviewQuestion.objects.create(session=session, question_text=first_question_text, sequence=1)
        cache.set(get_user_cache_key(request.user), str(session.id), timeout=7200)
        session_data = self.get_serializer(instance=session).data
        return Response(session_data, status=status.HTTP_201_CREATED)

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
        try:
            current_question = session.questions.get(id=question_id)
            current_question.answer_text = answer_text
            current_question.answered_at = timezone.now()
            if analysis_data: current_question.analysis_data = analysis_data
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        cache.touch(get_user_cache_key(request.user), timeout=7200)

        feedback_text = analyze_answer(session.job_position, current_question.question_text, answer_text, request.user)
        current_question.ai_feedback = {"feedback": feedback_text}
        current_question.save()

        answered_count = session.questions.filter(answered_at__isnull=False).count()
        if answered_count >= session.question_count:
            return Response({"feedback": feedback_text, "interview_finished": True}, status=status.HTTP_200_OK)

        history = [{'question': q.question_text, 'answer': q.answer_text} for q in
                   session.questions.filter(answered_at__isnull=False).order_by('sequence')]

        def stream_response_generator():
            question_buffer = []
            stream = generate_next_question_stream(session.job_position, history, request.user)
            for chunk in stream:
                question_buffer.append(chunk)
                yield chunk
            full_question_text = "".join(question_buffer)
            InterviewQuestion.objects.create(session=session, question_text=full_question_text,
                                             sequence=answered_count + 1)

        response = StreamingHttpResponse(stream_response_generator(), content_type='text/plain; charset=utf-8')
        response['X-Feedback'] = quote(feedback_text)
        response['Access-Control-Expose-Headers'] = 'X-Feedback'
        return response

    @action(detail=True, methods=['post'], url_path='finish')
    def finish_interview(self, request, pk=None):
        session = self.get_object()
        cache_key = get_user_cache_key(request.user)
        cache.delete(cache_key)

        if session.report:
            return Response(session.report, status=status.HTTP_200_OK)

        history = []
        answered_questions = session.questions.filter(answered_at__isnull=False).order_by('sequence')
        for q in answered_questions:
            history.append({
                'question': q.question_text,
                'answer': q.answer_text,
                'analysis_data': q.analysis_data
            })
        if not history:
            return Response({"error": "没有有效的问答记录，无法生成报告"}, status=status.HTTP_400_BAD_REQUEST)

        report_data = generate_final_report(job_position=session.job_position, interview_history=history,
                                            user=request.user)
        session.report = report_data
        session.status = InterviewSession.Status.FINISHED
        session.finished_at = timezone.now()
        session.save()
        return Response(report_data, status=status.HTTP_200_OK)


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
        jd_text = request.data.get('jd_text')

        if not resume_id or not jd_text:
            return Response({'error': '必须提供 resume_id 和 jd_text 字段'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resume_instance = Resume.objects.get(id=resume_id, user=request.user)
            resume_text = format_resume_to_text(resume_instance)
            if not resume_text.strip():
                return Response({'error': '无法从该简历中提取有效文本内容'}, status=status.HTTP_400_BAD_REQUEST)
        except Resume.DoesNotExist:
            return Response({'error': '简历不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 1. 调用AI服务
        analysis_report_data = analyze_resume_against_jd(
            resume_text=resume_text,
            jd_text=jd_text,
            user=request.user
        )

        if "error" in analysis_report_data:
            return Response(analysis_report_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 2. 【核心修改】将报告存入数据库
        try:
            new_report = ResumeAnalysisReport.objects.create(
                user=request.user,
                resume=resume_instance,
                jd_text=jd_text,
                report_data=analysis_report_data,
                overall_score=analysis_report_data.get('overall_score', 0)
            )
        except Exception as e:
            return Response({'error': f'保存分析报告失败: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 3. 序列化并返回新创建的报告对象
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