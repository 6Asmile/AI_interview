# interviews/serializers.py
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from .evaluation import can_manage_interview_system
from .models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunMetric,
    InterviewAgentMemoryEvent,
    InterviewAgentNodeRun,
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
    InterviewTemplateStage,
    RubricDimension,
    RubricLevelAnchor,
)

class StartInterviewSerializer(serializers.Serializer):
    """
    用于接收开始面试请求的序列化器 (只用于输入验证)
    """
    job_position = serializers.CharField(max_length=100, required=True, help_text="目标岗位名称")
    # resume_id = serializers.IntegerField(required=False, help_text="可选的简历ID")
    # difficulty = serializers.ChoiceField(choices=InterviewSession.Difficulty.choices, required=False)
    resume_id = serializers.IntegerField(required=False, help_text="可选的简历ID")
    jd_text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True, help_text="可选的岗位JD文本")
    question_count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)
    recording_enabled = serializers.BooleanField(required=False, default=False, help_text="是否开启面试录像")
    template_id = serializers.IntegerField(required=False, allow_null=True, help_text="可选的面试模板ID")


    class Meta:
        fields = ['job_position', 'recording_enabled']


class InterviewQuestionSerializer(serializers.ModelSerializer):
    """
    用于展示面试问题的序列化器
    """
    class Meta:
        model = InterviewQuestion
        fields = '__all__'
        read_only_fields = ('question_plan', 'question_signature', 'target_dimension', 'generation_mode', 'validation_status')


class InterviewQuestionGenerationJobSerializer(serializers.ModelSerializer):
    is_stale = serializers.SerializerMethodField()
    retry_after_seconds = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()

    class Meta:
        model = InterviewQuestionGenerationJob
        fields = [
            'id',
            'session',
            'answered_question',
            'generated_question',
            'sequence',
            'status',
            'request_hash',
            'engine_name',
            'partial_text',
            'final_text',
            'error_message',
            'started_at',
            'completed_at',
            'is_stale',
            'retry_after_seconds',
            'can_retry',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def _stale_seconds(self) -> int:
        return int(getattr(settings, 'INTERVIEW_GENERATION_JOB_STALE_SECONDS', 90))

    def _age_seconds(self, obj: InterviewQuestionGenerationJob) -> int:
        checkpoint = obj.updated_at or obj.started_at or obj.created_at
        if not checkpoint:
            return 0
        return max(0, int((timezone.now() - checkpoint).total_seconds()))

    def get_is_stale(self, obj: InterviewQuestionGenerationJob) -> bool:
        if obj.status != InterviewQuestionGenerationJob.Status.RUNNING:
            return False
        return self._age_seconds(obj) >= self._stale_seconds()

    def get_retry_after_seconds(self, obj: InterviewQuestionGenerationJob) -> int:
        if obj.status != InterviewQuestionGenerationJob.Status.RUNNING:
            return 0
        return max(0, self._stale_seconds() - self._age_seconds(obj))

    def get_can_retry(self, obj: InterviewQuestionGenerationJob) -> bool:
        if obj.status == InterviewQuestionGenerationJob.Status.FAILED:
            return True
        return self.get_is_stale(obj)


class InterviewSessionSerializer(serializers.ModelSerializer):
    """
    用于展示面试会话详细信息的序列化器
    """
    # 使用嵌套序列化器，在获取会话详情时，一并返回所有关联的问题
    questions = InterviewQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = InterviewSession
        fields = '__all__'


class InterviewAgentTraceSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAgentTrace
        fields = [
            'id',
            'agent_run',
            'session',
            'question',
            'event',
            'stage',
            'node_outputs',
            'answer_evaluation',
            'rag_context',
            'question_plan',
            'generated_question',
            'fallback_reason',
            'input_hash',
            'output_summary',
            'validation_errors',
            'model_config_snapshot',
            'subagent_name',
            'loop_iteration',
            'context_budget',
            'prompt_version',
            'compressed_context_summary',
            'created_at',
        ]
        read_only_fields = fields


class InterviewAgentNodeRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAgentNodeRun
        fields = [
            'id', 'node_name', 'subagent_name', 'status', 'attempt', 'input_hash',
            'output_summary', 'error_message', 'fallback_reason', 'latency_ms',
            'token_usage', 'started_at', 'completed_at', 'created_at',
        ]
        read_only_fields = fields


class InterviewAgentRunSerializer(serializers.ModelSerializer):
    node_runs = serializers.SerializerMethodField()

    class Meta:
        model = InterviewAgentRun
        fields = [
            'id', 'session', 'trigger_question', 'event', 'request_hash', 'engine_name',
            'status', 'state_schema_version', 'current_node', 'attempt_count',
            'fallback_reason', 'error_message', 'model_config_snapshot', 'prompt_version',
            'started_at', 'completed_at', 'created_at', 'updated_at', 'node_runs',
        ]
        read_only_fields = fields

    def get_node_runs(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not (
            getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'role', '') in ('admin', 'hr')
        ):
            return []
        return InterviewAgentNodeRunSerializer(obj.node_runs.order_by('created_at', 'id'), many=True).data


class InterviewAgentToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAgentToolCall
        fields = [
            'id',
            'session',
            'question',
            'trace',
            'event',
            'node_name',
            'tool_name',
            'subagent_name',
            'permission_scope',
            'status',
            'input_summary',
            'output_summary',
            'retrieval_trace',
            'error_message',
            'fallback_reason',
            'latency_ms',
            'created_at',
        ]
        read_only_fields = fields


class InterviewAgentMemoryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAgentMemoryEvent
        fields = [
            'id',
            'session',
            'question',
            'trace',
            'event_type',
            'memory_key',
            'value_summary',
            'importance',
            'source_node',
            'expires_at',
            'created_at',
        ]
        read_only_fields = fields


class InterviewMediaArtifactSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InterviewMediaArtifact
        fields = [
            'id',
            'session',
            'question',
            'artifact_type',
            'status',
            'file_url',
            'mime_type',
            'transcript_text',
            'transcript_segments',
            'asr_confidence',
            'provider',
            'model_slug',
            'error_message',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.source_file:
            return ''
        request = self.context.get('request')
        url = obj.source_file.url
        return request.build_absolute_uri(url) if request else url


class RubricLevelAnchorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricLevelAnchor
        fields = ['id', 'level', 'min_score', 'max_score', 'description']


class RubricDimensionSerializer(serializers.ModelSerializer):
    anchors = RubricLevelAnchorSerializer(many=True, required=False)

    class Meta:
        model = RubricDimension
        fields = ['id', 'key', 'name', 'description', 'weight', 'min_coverage', 'order', 'rule_config', 'anchors']

    def create(self, validated_data):
        anchors = validated_data.pop('anchors', [])
        dimension = RubricDimension.objects.create(**validated_data)
        for anchor in anchors:
            RubricLevelAnchor.objects.create(dimension=dimension, **anchor)
        return dimension


class InterviewRubricSerializer(serializers.ModelSerializer):
    dimensions = RubricDimensionSerializer(many=True, required=False)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = InterviewRubric
        fields = [
            'id',
            'name',
            'description',
            'version',
            'visibility',
            'is_active',
            'created_by',
            'created_at',
            'updated_at',
            'dimensions',
            'can_edit',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'can_edit']

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return can_manage_interview_system(getattr(request, 'user', None)) and obj.visibility != InterviewRubric.Visibility.SYSTEM

    def create(self, validated_data):
        dimensions = validated_data.pop('dimensions', [])
        rubric = InterviewRubric.objects.create(**validated_data)
        for dimension_data in dimensions:
            anchors = dimension_data.pop('anchors', [])
            dimension = RubricDimension.objects.create(rubric=rubric, **dimension_data)
            for anchor in anchors:
                RubricLevelAnchor.objects.create(dimension=dimension, **anchor)
        return rubric


class InterviewTemplateStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewTemplateStage
        fields = ['id', 'stage_key', 'name', 'order', 'question_ratio', 'target_dimensions', 'question_guidance']


class InterviewTemplateSerializer(serializers.ModelSerializer):
    stages = InterviewTemplateStageSerializer(many=True, required=False)
    rubric_detail = InterviewRubricSerializer(source='rubric', read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = InterviewTemplate
        fields = [
            'id',
            'name',
            'description',
            'job_keywords',
            'rubric',
            'rubric_detail',
            'visibility',
            'is_active',
            'version',
            'require_rag',
            'config',
            'created_by',
            'created_at',
            'updated_at',
            'stages',
            'can_edit',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'can_edit']

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return can_manage_interview_system(getattr(request, 'user', None)) and obj.visibility != InterviewTemplate.Visibility.SYSTEM

    def create(self, validated_data):
        stages = validated_data.pop('stages', [])
        template = InterviewTemplate.objects.create(**validated_data)
        for stage in stages:
            InterviewTemplateStage.objects.create(template=template, **stage)
        return template

    def update(self, instance, validated_data):
        stages = validated_data.pop('stages', None)
        instance = super().update(instance, validated_data)
        if stages is not None:
            instance.stages.all().delete()
            for stage in stages:
                InterviewTemplateStage.objects.create(template=instance, **stage)
        return instance


class InterviewCalibrationCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewCalibrationCase
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at']


class EvaluationCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationCase
        fields = ['id', 'job_position', 'jd_text', 'resume_text', 'question', 'answer', 'contexts', 'expected_dimensions', 'expected_follow_up', 'ground_truth', 'created_at']
        read_only_fields = ['created_at']


class EvaluationDatasetSerializer(serializers.ModelSerializer):
    cases = EvaluationCaseSerializer(many=True, required=False)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationDataset
        fields = ['id', 'name', 'description', 'visibility', 'created_by', 'created_at', 'updated_at', 'cases', 'can_edit']
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'can_edit']

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return can_manage_interview_system(getattr(request, 'user', None))

    def create(self, validated_data):
        cases = validated_data.pop('cases', [])
        dataset = EvaluationDataset.objects.create(**validated_data)
        for case in cases:
            EvaluationCase.objects.create(dataset=dataset, **case)
        return dataset


class EvaluationRunMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationRunMetric
        fields = ['id', 'case', 'metric_name', 'score', 'detail', 'created_at']


class EvaluationRunSerializer(serializers.ModelSerializer):
    metrics = EvaluationRunMetricSerializer(many=True, read_only=True)

    class Meta:
        model = EvaluationRun
        fields = [
            'id',
            'dataset',
            'template',
            'status',
            'config_snapshot',
            'summary',
            'error_message',
            'created_by',
            'started_at',
            'finished_at',
            'created_at',
            'metrics',
        ]
        read_only_fields = ['status', 'summary', 'error_message', 'created_by', 'started_at', 'finished_at', 'created_at', 'metrics']

class SubmitAnswerSerializer(serializers.Serializer):
    """
    用于接收用户回答的序列化器 (只用于输入)
    """
    question_id = serializers.IntegerField(required=True, help_text="当前回答的问题ID")
    answer_text = serializers.CharField(required=True, allow_blank=False, help_text="用户的回答文本")

    # 新增：接收一个 JSON 格式的数据，设为非必需
    analysis_data = serializers.JSONField(required=False)
    audio_artifact_id = serializers.UUIDField(required=False, allow_null=True)
    asr_transcript_meta = serializers.JSONField(required=False)

    class Meta:
        fields = ['question_id', 'answer_text', 'analysis_data', 'audio_artifact_id', 'asr_transcript_meta']


class RegenerateNextQuestionSerializer(serializers.Serializer):
    """
    用于在回答已保存但流式下一题生成失败时恢复下一题。
    """
    question_id = serializers.IntegerField(required=True, help_text="已提交回答的问题ID")


class FinishInterviewSerializer(serializers.Serializer):
    """
    用于接收面试结束时的录像数据
    """
    recording_data = serializers.JSONField(required=False, help_text="录像数据，包含文件标识、大小、分片数等")
    video_upload_id = serializers.CharField(required=False, allow_null=True, help_text="视频上传任务ID")


class InterviewRecordingSerializer(serializers.Serializer):
    """
    面试录像信息序列化器
    """
    video_url = serializers.URLField(allow_null=True)
    video_status = serializers.CharField()
    video_progress = serializers.IntegerField()
    compression_ratio = serializers.FloatField(allow_null=True)
