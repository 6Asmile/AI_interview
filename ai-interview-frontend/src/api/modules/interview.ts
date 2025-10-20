// src/api/modules/interview.ts
import { useAuthStore } from '@/store/modules/auth';
import request from '@/api/request';
import { getInterviewReportApi as getReportApi } from './report';

// --- 类型定义 ---
export interface UserInfo { id: number; username: string; email: string; }

// [核心修正] 将 action 设为可选字段，以匹配我们移除动作分析后的数据结构
export interface AnalysisFrame { timestamp: number; emotions: Record<string, number>; action?: string; } 

export interface InterviewQuestionItem { id: number; question_text: string; sequence: number; answer_text: string; ai_feedback?: { feedback?: string }; analysis_data?: AnalysisFrame[]; }
export interface InterviewSessionItem { id: string; user: UserInfo; job_position: string; status: string; question_count: number; questions: InterviewQuestionItem[]; started_at: string; }
export interface StartInterviewData { job_position: string; resume_id?: number; question_count?: number; }
export interface SubmitAnswerData { question_id: number; answer_text: string; analysis_data?: AnalysisFrame[]; }
export interface SubmitAnswerResponse { feedback: string; next_question?: InterviewQuestionItem; interview_finished?: boolean; }
export interface UnfinishedCheckResponse { has_unfinished: boolean; session_id?: string; job_position?: string; }

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

// --- 流式 API ---
export const submitAnswerStreamApi = async (
  sessionId: string,
  data: SubmitAnswerData,
  onDelta: (chunk: string) => void
): Promise<{ feedback: string; isFinished: boolean; }> => {
  const authStore = useAuthStore();
  
  const baseUrl = import.meta.env.VITE_API_BASE_URL.replace(/\/api\/v1\/?$/, '');
  const finalUrl = `${baseUrl}/api/v1/interviews/${sessionId}/submit-answer-stream/`;
  
  const response = await fetch(finalUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authStore.token}` },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('服务器响应错误');
  }

  if (response.headers.get('Content-Type')?.includes('application/json')) {
    const result = await response.json();
    if (result.interview_finished) {
      return { feedback: result.feedback || '', isFinished: true };
    }
  }

  if (!response.body) {
    throw new Error('响应体为空');
  }

  const feedback = response.headers.get('X-Feedback') || '';
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    onDelta(chunk);
  }

  return { feedback, isFinished: false };
};