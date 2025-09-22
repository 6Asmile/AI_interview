import request from '@/api/request';



// --- 类型定义 ---
interface UserInfo {
  id: number;
  username: string;
  email: string;
}

// 【核心修正 #1】为 AnalysisFrame 添加到这里，作为统一的类型源
export interface AnalysisFrame {
  timestamp: number;
  emotions: Record<string, number>;
  action: string;
}

export interface InterviewQuestionItem {
  id: number;
  question_text: string;
  sequence: number;
  answer_text: string;
  ai_feedback?: { feedback?: string };
  analysis_data?: AnalysisFrame[]; // 【核心修正 #2】在这里添加 analysis_data 字段
}

export interface InterviewSessionItem {
  id: string;
  user: UserInfo;
  job_position: string;
  status: string;
  question_count: number;
  questions: InterviewQuestionItem[];
  started_at: string;
}

export interface StartInterviewData {
  job_position: string;
  resume_id?: number;
  question_count?: number;
}

export interface SubmitAnswerData {
  question_id: number;
  answer_text: string;
  analysis_data?: AnalysisFrame[];
}

export interface SubmitAnswerResponse {
  feedback: string;
  next_question?: InterviewQuestionItem;
  interview_finished?: boolean;
}

export interface UnfinishedCheckResponse {
  has_unfinished: boolean;
  session_id?: string;
  job_position?: string;
}

// --- API 函数 (保持不变) ---
export const startInterviewApi = (data: StartInterviewData): Promise<InterviewSessionItem> => {
  return request({ url: '/interviews/start/', method: 'post', data });
};
export const getInterviewSessionApi = (sessionId: string): Promise<InterviewSessionItem> => {
  return request({ url: `/interviews/${sessionId}/`, method: 'get' });
};
export const submitAnswerApi = (sessionId: string, data: SubmitAnswerData): Promise<SubmitAnswerResponse> => {
  return request({ url: `/interviews/${sessionId}/submit-answer/`, method: 'post', data });
};
export const checkUnfinishedInterviewApi = (): Promise<UnfinishedCheckResponse> => {
  return request({ url: '/interviews/check-unfinished/', method: 'get' });
};
export const abandonUnfinishedInterviewApi = (): Promise<{ message: string }> => {
  return request({ url: '/interviews/abandon-unfinished/', method: 'post' });
};