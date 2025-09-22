from datetime import datetime
from django.core.cache import cache
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from resumes.models import Resume
from .models import InterviewSession, InterviewQuestion
from .serializers import InterviewSessionSerializer, StartInterviewSerializer, SubmitAnswerSerializer, \
    InterviewQuestionSerializer
from .ai_services import generate_first_question, analyze_and_generate_next, generate_final_report


def get_user_cache_key(user):
    return f"user_{user.id}_unfinished_interview"


class InterviewSessionViewSet(viewsets.ModelViewSet):
    queryset = InterviewSession.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InterviewSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return InterviewSessionSerializer

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

    # 【新增】放弃面试的 Action
    @action(detail=False, methods=['post'], url_path='abandon-unfinished')
    def abandon_unfinished(self, request):
        """
        用户选择放弃当前未完成的面试。
        """
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
                cache.delete(cache_key)  # 缓存冗余，清理掉
        return Response({"message": "没有需要放弃的面试"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='start')
    def start_interview(self, request):
        # 【核心改造】允许用户在有未完成面试时，选择放弃旧的并开始新的
        force_start = request.query_params.get('force', 'false').lower() == 'true'
        cache_key = get_user_cache_key(request.user)
        existing_session_id = cache.get(cache_key)

        if existing_session_id and not force_start:
            return Response(
                {"error": "您当前有一个正在进行的面试，请先处理。", "conflict_session_id": existing_session_id},
                status=status.HTTP_409_CONFLICT)

        if existing_session_id and force_start:
            # 强制开始新的，则将旧的标记为取消
            try:
                old_session = InterviewSession.objects.get(id=existing_session_id, user=request.user)
                old_session.status = InterviewSession.Status.CANCELED
                old_session.save()
            except InterviewSession.DoesNotExist:
                pass  # 如果不存在，忽略即可
            cache.delete(cache_key)

        serializer = StartInterviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job_position = serializer.validated_data['job_position']
        resume_id = serializer.validated_data.get('resume_id')
        question_count = serializer.validated_data.get('question_count')
        resume_instance = None
        resume_text = ""
        if resume_id:
            try:
                resume_instance = Resume.objects.get(id=resume_id, user=request.user)
                resume_text = resume_instance.parsed_content
            except Resume.DoesNotExist:
                return Response({"error": "简历不存在或不属于您"}, status=status.HTTP_404_NOT_FOUND)

        session = InterviewSession.objects.create(
            user=request.user, job_position=job_position, resume=resume_instance,
            question_count=question_count, status=InterviewSession.Status.RUNNING, started_at=datetime.now()
        )
        first_question_text = generate_first_question(job_position=job_position, user=request.user,
                                                      resume_text=resume_text)
        InterviewQuestion.objects.create(session=session, question_text=first_question_text, sequence=1)
        cache.set(cache_key, str(session.id), timeout=7200)
        session_data = self.get_serializer(instance=session).data
        return Response(session_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit-answer')
    def submit_answer(self, request, pk=None):
        """
        接收用户对特定问题的回答，保存分析数据，并返回下一个问题或结束信号。
        """
        session = self.get_object()
        cache_key = get_user_cache_key(request.user)

        if session.status != InterviewSession.Status.RUNNING:
            return Response({"error": "面试已结束或已取消，无法提交回答。"}, status=status.HTTP_400_BAD_REQUEST)

        cache.set(cache_key, str(session.id), timeout=7200)
        print(f"用户 {request.user.id} 的面试 {session.id} 缓存已刷新/重建。")

        serializer = SubmitAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data['question_id']
        answer_text = serializer.validated_data['answer_text']
        analysis_data = serializer.validated_data.get('analysis_data', None)

        try:
            current_question = session.questions.get(id=question_id)
            current_question.answer_text = answer_text
            current_question.answered_at = datetime.now()
            if analysis_data:
                current_question.analysis_data = analysis_data
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        history = []
        answered_questions_before_this = session.questions.filter(answered_at__isnull=False).exclude(
            id=question_id).order_by('sequence')
        for q in answered_questions_before_this:
            history.append({'question': q.question_text, 'answer': q.answer_text})

        history.append({'question': current_question.question_text, 'answer': answer_text})

        ai_response = analyze_and_generate_next(
            job_position=session.job_position,
            interview_history=history,
            user=request.user
        )

        current_question.ai_feedback = {"feedback": ai_response.get("feedback")}
        current_question.save()

        answered_count = answered_questions_before_this.count() + 1

        if answered_count >= session.question_count:
            return Response({
                "feedback": ai_response.get("feedback"),
                "interview_finished": True,
            }, status=status.HTTP_200_OK)
        else:
            next_question = InterviewQuestion.objects.create(
                session=session,
                question_text=ai_response.get("next_question"),
                sequence=answered_count + 1
            )
            return Response({
                "feedback": ai_response.get("feedback"),
                "next_question": InterviewQuestionSerializer(next_question).data
            }, status=status.HTTP_201_CREATED)

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