from datetime import datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from resumes.models import Resume
from .models import InterviewSession, InterviewQuestion
from .serializers import InterviewSessionSerializer, StartInterviewSerializer, SubmitAnswerSerializer, \
    InterviewQuestionSerializer
from .ai_services import generate_first_question, analyze_and_generate_next, generate_final_report


class InterviewSessionViewSet(viewsets.ModelViewSet):
    queryset = InterviewSession.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InterviewSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return InterviewSessionSerializer

    @action(detail=False, methods=['post'], url_path='start')
    def start_interview(self, request):
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
            user=request.user,
            job_position=job_position,
            resume=resume_instance,
            question_count=question_count,
            status=InterviewSession.Status.RUNNING,
            started_at=datetime.now()
        )

        first_question_text = generate_first_question(
            job_position=job_position,
            user=request.user,
            resume_text=resume_text
        )
        InterviewQuestion.objects.create(session=session, question_text=first_question_text, sequence=1)

        session_data = self.get_serializer(instance=session).data
        return Response(session_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit-answer')
    def submit_answer(self, request, pk=None):
        session = self.get_object()
        serializer = SubmitAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data['question_id']
        answer_text = serializer.validated_data['answer_text']

        try:
            current_question = session.questions.get(id=question_id)
            current_question.answer_text = answer_text
            current_question.answered_at = datetime.now()
            # 简评由AI生成后一起保存
        except InterviewQuestion.DoesNotExist:
            return Response({"error": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        # 【核心修正】
        # 先查询数据库中除当前问题外的、所有已回答的历史问题
        history = []
        answered_questions_before_this = session.questions.filter(answered_at__isnull=False).exclude(
            id=question_id).order_by('sequence')
        for q in answered_questions_before_this:
            history.append({'question': q.question_text, 'answer': q.answer_text})

        # 然后，手动将当前问题的问答对追加到历史记录的末尾
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

        if session.report:
            print(f"报告已存在，直接返回 session {session.id} 的报告。")
            return Response(session.report, status=status.HTTP_200_OK)

        history = []
        answered_questions = session.questions.filter(answered_at__isnull=False).order_by('sequence')
        for q in answered_questions:
            history.append({'question': q.question_text, 'answer': q.answer_text})

        if not history:
            return Response({"error": "没有有效的问答记录，无法生成报告"}, status=status.HTTP_400_BAD_REQUEST)

        print(f"正在为 session {session.id} 生成新报告...")
        report_data = generate_final_report(
            job_position=session.job_position,
            interview_history=history,
            user=request.user
        )

        session.report = report_data
        session.status = InterviewSession.Status.FINISHED
        session.finished_at = datetime.now()
        session.save()
        print(f"session {session.id} 的报告已生成并保存。")

        return Response(report_data, status=status.HTTP_200_OK)