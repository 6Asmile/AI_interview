import { useAuthStore } from '@/store/modules/auth';
import request from '@/api/request';

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
// 【终极核心】这个非流式接口现在是我们的主力
export const startInterviewApi = (data: StartInterviewData, force: boolean = false): Promise<InterviewSessionItem> => {
  return request({ url: `/interviews/start/?force=${force}`, method: 'post', data });
};
// --- 流式 API ---
// export const startInterviewStreamApi = async (data: StartInterviewData, onDelta: (chunk: string) => void): Promise<{ sessionId: string }> => {
//   const authStore = useAuthStore();
//   const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/interviews/start-stream/`, {
//     method: 'POST',
//     headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authStore.token}` },
//     body: JSON.stringify(data),
//   });

//   // 【核心修正】在使用前检查 response.body 是否为 null
//   if (!response.ok || !response.body) {
//     throw new Error('开启流式面试失败');
//   }

//   const sessionId = response.headers.get('X-Session-Id') || '';
//   if (!sessionId) { throw new Error('未在响应头中找到 Session ID'); }

//   const reader = response.body.getReader();
//   const decoder = new TextDecoder();
//   while (true) {
//     const { done, value } = await reader.read();
//     if (done) break;
//     onDelta(decoder.decode(value));
//   }
//   return { sessionId };
// };

export const submitAnswerStreamApi = async (sessionId: string, data: SubmitAnswerData, onDelta: (chunk: string) => void): Promise<{ feedback: string; interview_finished: boolean; }> => {
  const authStore = useAuthStore();
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/interviews/${sessionId}/submit-answer-stream/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authStore.token}` },
    body: JSON.stringify(data),
  });

  if (response.headers.get('Content-Type')?.includes('application/json')) {
    const result = await response.json();
    return { feedback: result.feedback || '', interview_finished: result.interview_finished || false };
  }
  
  // 【核心修正】在使用前检查 response.body 是否为 null
  if (!response.ok || !response.body) {
    throw new Error('提交回答失败');
  }

  const feedback = response.headers.get('X-Feedback') || '';
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onDelta(decoder.decode(value));
  }
  return { feedback, interview_finished: false };
};