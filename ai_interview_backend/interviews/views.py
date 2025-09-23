from datetime import datetime
from django.http import StreamingHttpResponse
from django.core.cache import cache
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from resumes.models import Resume
from .models import InterviewSession, InterviewQuestion
from .serializers import InterviewSessionSerializer, StartInterviewSerializer, SubmitAnswerSerializer, InterviewQuestionSerializer
from .ai_services import (
    generate_first_question, # 使用非流式
    analyze_answer,
    generate_next_question_stream,
    generate_final_report
)

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

        # 【终极核心】回归到这个稳健的、非流式的启动接口

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
        resume_instance, resume_text = None, ""
        if resume_id:
            try:
                resume_instance = Resume.objects.get(id=resume_id, user=request.user)
                resume_text = resume_instance.parsed_content
            except Resume.DoesNotExist:
                return Response({"error": "简历不存在"}, status=status.HTTP_404_NOT_FOUND)

        session = InterviewSession.objects.create(
            user=request.user, job_position=job_position, resume=resume_instance,
            question_count=question_count, status=InterviewSession.Status.RUNNING, started_at=datetime.now()
        )

        # 调用非流式的 AI 服务
        first_question_text = generate_first_question(job_position, request.user, resume_text)

        InterviewQuestion.objects.create(session=session, question_text=first_question_text, sequence=1)
        cache.set(cache_key, str(session.id), timeout=7200)

        # 返回完整的会话数据
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
            current_question.answered_at = datetime.now()
            if analysis_data: current_question.analysis_data = analysis_data
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        cache.touch(get_user_cache_key(request.user), timeout=7200)
        answered_questions = session.questions.filter(answered_at__isnull=False).order_by('sequence')
        history = [{'question': q.question_text, 'answer': q.answer_text} for q in answered_questions]

        feedback_text = analyze_answer(session.job_position, current_question.question_text, answer_text, request.user)
        current_question.ai_feedback = {"feedback": feedback_text}
        current_question.save()

        if answered_questions.count() >= session.question_count:
            return Response({"feedback": feedback_text, "interview_finished": True}, status=status.HTTP_200_OK)

        def stream_response_generator():
            question_buffer = []
            stream = generate_next_question_stream(session.job_position, history, request.user)
            for chunk in stream:
                question_buffer.append(chunk)
                yield chunk
            full_question_text = "".join(question_buffer)
            next_question = InterviewQuestion.objects.create(session=session, question_text=full_question_text,
                                                             sequence=answered_questions.count() + 1)
            print(f"已为会话 {session.id} 保存下一个问题 (ID: {next_question.id})。")

        response = StreamingHttpResponse(stream_response_generator(), content_type='text/plain; charset=utf-8')
        response['X-Feedback'] = feedback_text
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
                'analysis_data': q.analysis_data  # <-- 就是这一行！
            })
        if not history:
            return Response({"error": "没有有效的问答记录，无法生成报告"}, status=status.HTTP_400_BAD_REQUEST)

        report_data = generate_final_report(job_position=session.job_position, interview_history=history,
                                            user=request.user)
        session.report = report_data
        session.status = InterviewSession.Status.FINISHED
        session.finished_at = datetime.now()
        session.save()
        return Response(report_data, status=status.HTTP_200_OK)