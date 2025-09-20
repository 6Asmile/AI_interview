# interviews/serializers.py
from rest_framework import serializers
from .models import InterviewSession, InterviewQuestion

class StartInterviewSerializer(serializers.Serializer):
    """
    用于接收开始面试请求的序列化器 (只用于输入验证)
    """
    job_position = serializers.CharField(max_length=100, required=True, help_text="目标岗位名称")
    # resume_id = serializers.IntegerField(required=False, help_text="可选的简历ID")
    # difficulty = serializers.ChoiceField(choices=InterviewSession.Difficulty.choices, required=False)
    resume_id = serializers.IntegerField(required=False, help_text="可选的简历ID")
    question_count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)


    class Meta:
        fields = ['job_position']


class InterviewQuestionSerializer(serializers.ModelSerializer):
    """
    用于展示面试问题的序列化器
    """
    class Meta:
        model = InterviewQuestion
        fields = '__all__'


class InterviewSessionSerializer(serializers.ModelSerializer):
    """
    用于展示面试会话详细信息的序列化器
    """
    # 使用嵌套序列化器，在获取会话详情时，一并返回所有关联的问题
    questions = InterviewQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = InterviewSession
        fields = '__all__'

class SubmitAnswerSerializer(serializers.Serializer):
    """
    用于接收用户回答的序列化器 (只用于输入)
    """
    question_id = serializers.IntegerField(required=True, help_text="当前回答的问题ID")
    answer_text = serializers.CharField(required=True, allow_blank=False, help_text="用户的回答文本")

    class Meta:
        fields = ['question_id', 'answer_text']