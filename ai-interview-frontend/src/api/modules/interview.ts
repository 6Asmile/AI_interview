// src/api/modules/interview.ts
import { useAuthStore } from '@/store/modules/auth';
import request from '@/api/request';
import { getInterviewReportApi as getReportApi } from './report';

// --- 类型定义 ---
export interface UserInfo { id: number; username: string; email: string; }
export interface AnalysisFrame { timestamp: number; emotions: Record<string, number>; action: string; }
export interface InterviewQuestionItem { id: number; question_text: string; sequence: number; answer_text: string; ai_feedback?: { feedback?: string }; analysis_data?: AnalysisFrame[]; }
export interface InterviewSessionItem { id: string; user: UserInfo; job_position: string; status: string; question_count: number; questions: InterviewQuestionItem[]; started_at: string; }
export interface StartInterviewData { job_position: string; resume_id?: number; question_count?: number; }
export interface SubmitAnswerData { question_id: number; answer_text: string; analysis_data?: AnalysisFrame[]; }
export interface SubmitAnswerResponse { feedback: string; next_question?: InterviewQuestionItem; interview_finished?: boolean; }
export interface UnfinishedCheckResponse { has_unfinished: boolean; session_id?: string; job_position?: string; }

// --- 非流式 API ---
export const getInterviewSessionApi = (sessionId: string): Promise<InterviewSessionItem> => { return request({ url: `/interviews/${sessionId}/`, method: 'get' }); };
export const checkUnfinishedInterviewApi = (): Promise<UnfinishedCheckResponse> => { return request({ url: '/interviews/check-unfinished/', method: 'get' }); };
export const abandonUnfinishedInterviewApi = (): Promise<{ message: string }> => { return request({ url: '/interviews/abandon-unfinished/', method: 'post' }); };
export const startInterviewApi = (data: StartInterviewData, force: boolean = false): Promise<InterviewSessionItem> => {
  return request({ url: `/interviews/start/?force=${force}`, method: 'post', data });
};
export const getInterviewReportApi = getReportApi;

// --- 流式 API ---
// 【终极核心修正】改造函数，使其返回一个包含最终结果的 Promise
export const submitAnswerStreamApi = async (
  sessionId: string,
  data: SubmitAnswerData,
  onDelta: (chunk: string) => void // 回调函数现在只负责传递文本块
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

  // 情况一：面试结束，返回JSON
  if (response.headers.get('Content-Type')?.includes('application/json')) {
    const result = await response.json();
    if (result.interview_finished) {
      return { feedback: result.feedback || '', isFinished: true };
    }
  }

  // 情况二：正常流式响应
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
    onDelta(chunk); // 只传递文本块
  }

  // 流结束后，返回最终的反馈和未结束状态
  return { feedback, isFinished: false };
};