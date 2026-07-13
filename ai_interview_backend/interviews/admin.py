# interviews/admin.py
from django.contrib import admin
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

class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0  # 默认不显示额外空行
    readonly_fields = ('created_at', 'answered_at', 'evaluated_at')

@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('job_position', 'user', 'status', 'interview_mode', 'experience_mode', 'progress_mode', 'target_duration_minutes', 'created_at')
    list_filter = ('status', 'difficulty', 'interview_mode', 'experience_mode', 'progress_mode', 'user')
    search_fields = ('job_position', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'finished_at')
    inlines = [InterviewQuestionInline] # 在会话详情页直接显示关联的问题

@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('sequence', 'question_text', 'session', 'target_dimension', 'generation_mode', 'validation_status', 'score', 'answered_at')
    list_filter = ('session__job_position', 'generation_mode', 'validation_status', 'target_dimension')
    search_fields = ('question_text', 'answer_text')


@admin.register(InterviewQuestionGenerationJob)
class InterviewQuestionGenerationJobAdmin(admin.ModelAdmin):
    list_display = ('session', 'sequence', 'status', 'engine_name', 'started_at', 'completed_at', 'updated_at')
    list_filter = ('status', 'engine_name')
    search_fields = ('session__job_position', 'partial_text', 'final_text', 'error_message', 'request_hash')
    readonly_fields = (
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
        'created_at',
        'updated_at',
    )


@admin.register(InterviewAgentTrace)
class InterviewAgentTraceAdmin(admin.ModelAdmin):
    list_display = ('session', 'event', 'stage', 'fallback_reason', 'created_at')
    list_filter = ('event', 'stage', 'fallback_reason')
    search_fields = ('session__job_position', 'generated_question')
    readonly_fields = (
        'session',
        'agent_run',
        'question',
        'event',
        'stage',
        'node_outputs',
        'answer_evaluation',
        'rag_context',
        'question_plan',
        'generated_question',
        'fallback_reason',
        'created_at',
    )


class InterviewAgentNodeRunInline(admin.TabularInline):
    model = InterviewAgentNodeRun
    extra = 0
    can_delete = False
    readonly_fields = (
        'node_name', 'subagent_name', 'status', 'attempt', 'input_hash',
        'output_summary', 'error_message', 'fallback_reason', 'latency_ms',
        'token_usage', 'started_at', 'completed_at', 'created_at',
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InterviewAgentRun)
class InterviewAgentRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'event', 'status', 'current_node', 'attempt_count', 'engine_name', 'updated_at')
    list_filter = ('status', 'event', 'engine_name', 'state_schema_version')
    search_fields = ('id', 'session__job_position', 'request_hash', 'error_message')
    readonly_fields = (
        'id', 'session', 'trigger_question', 'event', 'request_hash', 'engine_name',
        'status', 'state_schema_version', 'current_node', 'attempt_count',
        'state_snapshot', 'fallback_reason', 'error_message', 'model_config_snapshot',
        'prompt_version', 'started_at', 'completed_at', 'created_at', 'updated_at',
    )
    inlines = [InterviewAgentNodeRunInline]

    def has_add_permission(self, request):
        return False


@admin.register(InterviewAgentNodeRun)
class InterviewAgentNodeRunAdmin(admin.ModelAdmin):
    list_display = ('run', 'node_name', 'subagent_name', 'status', 'attempt', 'latency_ms', 'created_at')
    list_filter = ('status', 'node_name', 'subagent_name')
    search_fields = ('run__id', 'run__session__job_position', 'error_message')
    readonly_fields = (
        'run', 'node_name', 'subagent_name', 'status', 'attempt', 'input_hash',
        'output_summary', 'error_message', 'fallback_reason', 'latency_ms',
        'token_usage', 'started_at', 'completed_at', 'created_at',
    )

    def has_add_permission(self, request):
        return False


@admin.register(InterviewAgentToolCall)
class InterviewAgentToolCallAdmin(admin.ModelAdmin):
    list_display = ('session', 'event', 'node_name', 'tool_name', 'status', 'created_at')
    list_filter = ('event', 'node_name', 'tool_name', 'status')
    search_fields = ('session__job_position', 'tool_name', 'error_message')
    readonly_fields = (
        'session',
        'question',
        'trace',
        'event',
        'node_name',
        'tool_name',
        'status',
        'input_summary',
        'output_summary',
        'retrieval_trace',
        'error_message',
        'latency_ms',
        'created_at',
    )


@admin.register(InterviewAgentMemoryEvent)
class InterviewAgentMemoryEventAdmin(admin.ModelAdmin):
    list_display = ('session', 'event_type', 'memory_key', 'importance', 'source_node', 'created_at')
    list_filter = ('event_type', 'importance', 'source_node')
    search_fields = ('session__job_position', 'memory_key')
    readonly_fields = (
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
    )


@admin.register(InterviewMediaArtifact)
class InterviewMediaArtifactAdmin(admin.ModelAdmin):
    list_display = ('session', 'question', 'artifact_type', 'status', 'provider', 'model_slug', 'asr_confidence', 'created_at')
    list_filter = ('artifact_type', 'status', 'provider', 'model_slug')
    search_fields = ('session__job_position', 'user__username', 'transcript_text', 'error_message')
    readonly_fields = (
        'id',
        'session',
        'question',
        'user',
        'artifact_type',
        'status',
        'source_file',
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
    )


class RubricDimensionInline(admin.TabularInline):
    model = RubricDimension
    extra = 0


class TemplateStageInline(admin.TabularInline):
    model = InterviewTemplateStage
    extra = 0


class EvaluationCaseInline(admin.TabularInline):
    model = EvaluationCase
    extra = 0


class EvaluationRunMetricInline(admin.TabularInline):
    model = EvaluationRunMetric
    extra = 0
    readonly_fields = ('metric_name', 'score', 'detail', 'created_at')


@admin.register(InterviewRubric)
class InterviewRubricAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'visibility', 'is_active', 'updated_at')
    list_filter = ('visibility', 'is_active')
    search_fields = ('name', 'description')
    inlines = [RubricDimensionInline]


@admin.register(RubricLevelAnchor)
class RubricLevelAnchorAdmin(admin.ModelAdmin):
    list_display = ('dimension', 'level', 'min_score', 'max_score')
    list_filter = ('level',)


@admin.register(InterviewTemplate)
class InterviewTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'rubric', 'interview_mode', 'target_duration_minutes', 'min_turns', 'max_turns', 'visibility', 'is_active', 'updated_at')
    list_filter = ('interview_mode', 'visibility', 'is_active', 'require_rag')
    search_fields = ('name', 'description')
    inlines = [TemplateStageInline]


@admin.register(InterviewCalibrationCase)
class InterviewCalibrationCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'rubric', 'job_position', 'created_at')
    search_fields = ('title', 'job_position', 'question', 'answer')


@admin.register(EvaluationDataset)
class EvaluationDatasetAdmin(admin.ModelAdmin):
    list_display = ('name', 'visibility', 'created_by', 'updated_at')
    list_filter = ('visibility',)
    search_fields = ('name', 'description')
    inlines = [EvaluationCaseInline]


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ('dataset', 'template', 'status', 'created_by', 'created_at', 'finished_at')
    list_filter = ('status',)
    readonly_fields = ('summary', 'error_message', 'started_at', 'finished_at', 'created_at')
    inlines = [EvaluationRunMetricInline]
