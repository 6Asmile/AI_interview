// src/api/modules/interview.ts
import { useAuthStore } from '@/store/modules/auth';
import request from '@/api/request';
import { getInterviewReportApi as getReportApi } from './report';

// --- 类型定义 ---
export interface UserInfo { id: number; username: string; email: string; }

// [核心修正] 将 action 设为可选字段，以匹配我们移除动作分析后的数据结构
export interface AnalysisFrame { timestamp: number; emotions: Record<string, number>; action?: string; } 

export type AnswerLevel = 'weak' | 'average' | 'solid' | 'strong';

export interface AnswerFeedback {
  feedback?: string;
  quality_score?: number;
  rule_score?: number;
  ai_score?: number | null;
  final_score?: number;
  evaluation_mode?: 'rule_ai_dual' | 'rule_only_degraded';
  degraded_reason?: string;
  rubric_scores?: Array<{ dimension_key: string; score: number; reason?: string }>;
  evidence_items?: Array<{ type: string; quote: string; supported: boolean }>;
  star_breakdown?: Record<string, boolean>;
  risk_flags?: string[];
  confidence?: number;
  clarity_score?: number;
  depth_score?: number;
  relevance_score?: number;
  evidence_score?: number;
  answer_level?: AnswerLevel;
  follow_up_target?: string;
  follow_up_reason?: string;
  should_escalate?: boolean;
}

export interface AgentMemorySummary {
  summary?: string;
  strengths?: string[];
  risks?: string[];
  covered_topics?: string[];
  pending_topics?: string[];
  question_strategy?: string;
  verified_abilities?: string[];
  unverified_risks?: string[];
  adaptive_difficulty?: 'easy' | 'medium' | 'hard';
  last_quality_score?: number;
  last_answer_level?: AnswerLevel;
  follow_up_target?: string;
  should_escalate?: boolean;
  rag_context_count?: number;
  last_rag_sources?: Array<{ title?: string; chunk_id?: string }>;
}

export interface RagContextItem {
  document_id?: string;
  chunk_id?: string;
  title?: string;
  content?: string;
  source_type?: string;
  job_positions?: string[];
  ability_tags?: string[];
  difficulty?: string;
  visibility?: 'private' | 'public';
  score?: number;
}

export interface InterviewQuestionItem { id: number; question_text: string; sequence: number; answer_text: string; ai_feedback?: AnswerFeedback; analysis_data?: AnalysisFrame[]; rag_context?: RagContextItem[]; audio_url?: string; }
export interface InterviewSessionItem { id: string; user: UserInfo; job_position: string; status: string; question_count: number; questions: InterviewQuestionItem[]; started_at: string; current_stage?: string; memory_summary?: AgentMemorySummary; covered_topics?: string[]; pending_topics?: string[]; recording_enabled?: boolean; video_upload_task?: string; session_plan?: Record<string, any>; template_snapshot?: Record<string, any>; coverage_summary?: Record<string, any>; target_duration_minutes?: number; experience_mode?: 'realistic' | 'coaching'; interview_mode?: string; progress_mode?: 'question_count' | 'time_and_coverage'; elapsed_seconds?: number; estimated_question_range?: { min: number; max: number }; }
export interface StartInterviewData { job_position: string; resume_id?: number; jd_text?: string; question_count?: number; target_duration_minutes?: number; interview_mode?: 'relaxed' | 'strict' | 'fundamentals' | 'project_deep_dive' | 'project_with_fundamentals' | 'system_design' | 'behavioral' | 'structured'; experience_mode?: 'realistic' | 'coaching'; recording_enabled?: boolean; difficulty?: 'easy' | 'medium' | 'hard'; template_id?: number | null; }
export interface SubmitAnswerData { question_id: number; answer_text: string; analysis_data?: AnalysisFrame[]; video_data?: string; video_upload_id?: string; audio_artifact_id?: string; asr_transcript_meta?: Record<string, any>; }
export interface SubmitAnswerResponse { feedback: string; feedback_detail?: AnswerFeedback; next_question?: InterviewQuestionItem; interview_finished?: boolean; }
export interface UnfinishedCheckResponse { has_unfinished: boolean; session_id?: string; job_position?: string; }

export class SubmitAnswerStreamError extends Error {
  generationJob?: InterviewQuestionGenerationJobItem;
  status?: number;

  constructor(message: string, options?: { generationJob?: InterviewQuestionGenerationJobItem; status?: number }) {
    super(message);
    this.name = 'SubmitAnswerStreamError';
    this.generationJob = options?.generationJob;
    this.status = options?.status;
  }
}

export interface InterviewMediaArtifact {
  id: string;
  session: string;
  question?: number | null;
  artifact_type: 'answer_audio' | 'question_tts';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  file_url?: string;
  mime_type?: string;
  transcript_text?: string;
  transcript_segments?: any[];
  asr_confidence?: number | null;
  provider?: string;
  model_slug?: string;
  error_message?: string;
  metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface QuestionTTSResponse {
  status: 'completed' | 'failed';
  artifact?: InterviewMediaArtifact;
  audio_url?: string;
  fallback?: 'browser_tts';
  error?: string;
  artifact_id?: string;
}

export interface InterviewAgentTraceItem {
  id: number;
  session: string;
  question?: number | null;
  event: string;
  stage?: string;
  node_outputs?: Record<string, any>;
  answer_evaluation?: AnswerFeedback;
  rag_context?: RagContextItem[];
  question_plan?: Record<string, any>;
  generated_question?: string;
  fallback_reason?: string;
  input_hash?: string;
  output_summary?: Record<string, any>;
  validation_errors?: string[];
  model_config_snapshot?: Record<string, any>;
  created_at: string;
}

export interface InterviewAgentToolCallItem {
  id: number;
  session: string;
  question?: number | null;
  trace?: number | null;
  event: string;
  node_name: string;
  tool_name: string;
  status: 'success' | 'degraded' | 'failed';
  input_summary?: Record<string, any>;
  output_summary?: Record<string, any>;
  retrieval_trace?: Record<string, any>;
  error_message?: string;
  latency_ms?: number | null;
  created_at: string;
}

export interface InterviewAgentMemoryEventItem {
  id: number;
  session: string;
  question?: number | null;
  trace?: number | null;
  event_type: 'observation' | 'plan' | 'coverage' | 'question' | 'environment';
  memory_key: string;
  value_summary?: Record<string, any>;
  importance: number;
  source_node?: string;
  expires_at?: string | null;
  created_at: string;
}

export interface InterviewQuestionGenerationJobItem {
  id: number;
  session: string;
  answered_question?: number | null;
  generated_question?: number | null;
  sequence: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  request_hash?: string;
  engine_name?: string;
  partial_text?: string;
  final_text?: string;
  error_message?: string;
  started_at?: string | null;
  completed_at?: string | null;
  is_stale?: boolean;
  retry_after_seconds?: number;
  can_retry?: boolean;
  created_at: string;
  updated_at: string;
}

export interface RecordingStatusResponse {
  has_recording: boolean;
  video_url: string | null;
  status: 'pending' | 'uploading' | 'transcoding' | 'completed' | 'failed' | null;
  progress: number;
  error_message: string | null;
  playback_source?: 'transcoded' | 'original' | null;
  fallback_available?: boolean;
  transcode_status?: 'pending' | 'processing' | 'completed' | 'failed' | null;
  transcode_progress?: number;
  transcode_error_message?: string | null;
}

export interface FinishInterviewData {
  video_data?: string;
  video_upload_id?: string;
}

export interface FinishInterviewResponse {
  [key: string]: any;
}

// [核心新增]
// 定义 AI 参考答案的响应类型
export interface AIReferenceAnswerResponse {
  answer: string;
}

// API: 获取 AI 参考答案
export const getAIReferenceAnswerApi = (questionId: number): Promise<AIReferenceAnswerResponse> => {
  return request({
    url: `/interviews/questions/${questionId}/reference-answer/`,
    method: 'get',
  });
};

// --- 非流式 API ---
export const getInterviewSessionApi = (sessionId: string): Promise<InterviewSessionItem> => { return request({ url: `/interviews/${sessionId}/`, method: 'get' }); };
export const checkUnfinishedInterviewApi = (): Promise<UnfinishedCheckResponse> => { return request({ url: '/interviews/check-unfinished/', method: 'get' }); };
export const abandonUnfinishedInterviewApi = (): Promise<{ message: string }> => { return request({ url: '/interviews/abandon-unfinished/', method: 'post' }); };
export const startInterviewApi = (data: StartInterviewData, force: boolean = false): Promise<InterviewSessionItem> => {
  return request({ url: `/interviews/start/?force=${force}`, method: 'post', data });
};
export const getInterviewReportApi = getReportApi;

export const getRecordingStatusApi = (sessionId: string): Promise<RecordingStatusResponse> => {
  return request({
    url: `/interviews/${sessionId}/recording/`,
    method: 'get',
  });
};

export const finishInterviewApi = (sessionId: string, data?: FinishInterviewData): Promise<FinishInterviewResponse> => {
  return request({
    url: `/interviews/${sessionId}/finish/`,
    method: 'post',
    data: data || {},
  });
};

export const regenerateNextQuestionApi = (
  sessionId: string,
  questionId: number
): Promise<{ next_question?: InterviewQuestionItem; feedback_detail?: AnswerFeedback; interview_finished?: boolean; already_exists?: boolean; generation_job?: InterviewQuestionGenerationJobItem }> => {
  return request({
    url: `/interviews/${sessionId}/regenerate-next-question/`,
    method: 'post',
    data: { question_id: questionId },
  });
};

export const generateQuestionTTSApi = (
  sessionId: string,
  questionId: number
): Promise<QuestionTTSResponse> => {
  return request({
    url: `/interviews/${sessionId}/questions/${questionId}/tts/`,
    method: 'post',
  });
};

export const getInterviewMediaArtifactsApi = (sessionId: string): Promise<InterviewMediaArtifact[]> => {
  return request({
    url: `/interviews/${sessionId}/media-artifacts/`,
    method: 'get',
  });
};

export const getInterviewAgentTracesApi = (sessionId: string): Promise<InterviewAgentTraceItem[]> => {
  return request({
    url: `/interviews/${sessionId}/agent-traces/`,
    method: 'get',
  });
};

export const getInterviewAgentToolCallsApi = (sessionId: string): Promise<InterviewAgentToolCallItem[]> => {
  return request({
    url: `/interviews/${sessionId}/agent-tool-calls/`,
    method: 'get',
  });
};

export const getInterviewAgentMemoryEventsApi = (sessionId: string): Promise<InterviewAgentMemoryEventItem[]> => {
  return request({
    url: `/interviews/${sessionId}/agent-memory-events/`,
    method: 'get',
  });
};

export const getInterviewQuestionGenerationJobsApi = (sessionId: string): Promise<InterviewQuestionGenerationJobItem[]> => {
  return request({
    url: `/interviews/${sessionId}/question-generation-jobs/`,
    method: 'get',
  });
};

// --- 流式 API ---
export const submitAnswerStreamApi = async (
  sessionId: string,
  data: SubmitAnswerData,
  onDelta: (chunk: string) => void,
  onGenerationJob?: (job: Partial<InterviewQuestionGenerationJobItem>) => void
): Promise<{ feedback: string; feedbackDetail?: AnswerFeedback; isFinished: boolean; generationJobId?: string; nextQuestion?: InterviewQuestionItem; }> => {
  const authStore = useAuthStore();
  
  const baseUrl = import.meta.env.VITE_API_BASE_URL.replace(/\/api\/v1\/?$/, '');
  const finalUrl = `${baseUrl}/api/v1/interviews/${sessionId}/submit-answer-stream/`;
  
  const response = await fetch(finalUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authStore.token}` },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let errorMessage = '服务器响应错误';
    let generationJob: InterviewQuestionGenerationJobItem | undefined;
    if (response.headers.get('Content-Type')?.includes('application/json')) {
      try {
        const errorResult = await response.json();
        errorMessage = errorResult.error || errorResult.detail || errorMessage;
        generationJob = errorResult.generation_job;
      } catch {
        // Keep the generic message when the server returns malformed JSON.
      }
    }
    throw new SubmitAnswerStreamError(errorMessage, { generationJob, status: response.status });
  }

  if (response.headers.get('Content-Type')?.includes('application/json')) {
    const result = await response.json();
    const generationJobId = result.generation_job?.id ? String(result.generation_job.id) : undefined;
    if (result.interview_finished) {
      return { feedback: result.feedback || '', feedbackDetail: result.feedback_detail, isFinished: true, generationJobId };
    }
    if (result.next_question?.question_text) {
      onDelta(result.next_question.question_text);
    }
    if (result.already_answered) {
      return { feedback: result.feedback || '', feedbackDetail: result.feedback_detail, isFinished: false, generationJobId, nextQuestion: result.next_question };
    }
    if (result.already_generated || result.next_question) {
      return { feedback: result.feedback || '', feedbackDetail: result.feedback_detail, isFinished: false, generationJobId, nextQuestion: result.next_question };
    }
    throw new Error(result.error || '提交已完成，但未获取到下一题。');
  }

  if (!response.body) {
    throw new Error('响应体为空');
  }

  const feedback = response.headers.get('X-Feedback') || '';
  const generationJobId = response.headers.get('X-Generation-Job-Id') || undefined;
  if (generationJobId) {
    onGenerationJob?.({
      id: Number(generationJobId),
      session: sessionId,
      answered_question: data.question_id,
      sequence: 0,
      status: 'running',
      partial_text: '',
      final_text: '',
      error_message: '',
      is_stale: false,
      retry_after_seconds: undefined,
      can_retry: false,
    });
  }
  const feedbackDetailHeader = response.headers.get('X-Feedback-Json');
  let feedbackDetail: AnswerFeedback | undefined;
  if (feedbackDetailHeader) {
    try {
      feedbackDetail = JSON.parse(decodeURIComponent(feedbackDetailHeader));
    } catch (error) {
      console.warn('Failed to parse X-Feedback-Json header', error);
    }
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let streamBuffer = '';
  let finalQuestion: InterviewQuestionItem | undefined;
  const finalMarker = '\n__FINAL_QUESTION__:';
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    streamBuffer += chunk;
    const markerIndex = streamBuffer.indexOf(finalMarker);
    if (markerIndex >= 0) {
      const visibleChunk = streamBuffer.slice(0, markerIndex);
      if (visibleChunk) onDelta(visibleChunk);
      const payloadText = streamBuffer.slice(markerIndex + finalMarker.length).trim();
      if (payloadText) {
        try {
          finalQuestion = JSON.parse(payloadText);
        } catch (error) {
          console.warn('Failed to parse final question marker', error);
        }
      }
      streamBuffer = '';
      continue;
    }
    if (streamBuffer.length > finalMarker.length) {
      const emitLength = streamBuffer.length - finalMarker.length;
      const visibleChunk = streamBuffer.slice(0, emitLength);
      streamBuffer = streamBuffer.slice(emitLength);
      if (visibleChunk) onDelta(visibleChunk);
    }
  }
  if (streamBuffer) onDelta(streamBuffer);

  return { feedback, feedbackDetail, isFinished: false, generationJobId, nextQuestion: finalQuestion };
};
