import request from '@/api/request';

// --- 类型定义 ---
// 用户信息，用于在报告页展示
interface UserInfo {
  id: number;
  username: string;
  email: string;
}

export interface InterviewQuestionItem {
  id: number;
  question_text: string;
  sequence: number;
  answer_text: string; // 新增：回答文本
  ai_feedback?: { feedback?: string };
}

export interface InterviewSessionItem {
  id: string; // UUID
  user: UserInfo; // 修正：定义 user 对象的类型
  job_position: string;
  status: string;
  question_count: number;
  questions: InterviewQuestionItem[];
  started_at: string; // 新增：开始时间
  // ...其他字段
}

export interface StartInterviewData {
  job_position: string;
  resume_id?: number;
  question_count?: number;
}

export interface SubmitAnswerData {
  question_id: number;
  answer_text: string;
}

export interface SubmitAnswerResponse {
  feedback: string;
  next_question?: InterviewQuestionItem;
  interview_finished?: boolean;
}

// --- API 函数 ---
export const startInterviewApi = (data: StartInterviewData, _force: boolean): Promise<InterviewSessionItem> => {
  return request({ url: '/interviews/start/', method: 'post', data });
};

export const getInterviewSessionApi = (sessionId: string): Promise<InterviewSessionItem> => {
  return request({ url: `/interviews/${sessionId}/`, method: 'get' });
};

export const submitAnswerApi = (sessionId: string, data: SubmitAnswerData): Promise<SubmitAnswerResponse> => {
  return request({ url: `/interviews/${sessionId}/submit-answer/`, method: 'post', data });
};
// 定义检查中断接口的响应类型
export interface UnfinishedCheckResponse {
  has_unfinished: boolean;
  session_id?: string;
  job_position?: string;
}

// API: 检查是否有未完成的面试
export const checkUnfinishedInterviewApi = (): Promise<UnfinishedCheckResponse> => {
  return request({
    url: '/interviews/check-unfinished/',
    method: 'get',
  });
};

// 【新增】放弃未完成面试的 API
export const abandonUnfinishedInterviewApi = (): Promise<{ message: string }> => {
  return request({ url: '/interviews/abandon-unfinished/', method: 'post' });
};