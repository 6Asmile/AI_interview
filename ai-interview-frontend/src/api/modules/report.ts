import request from '@/api/request';
import type { InterviewSessionItem } from './interview';

// 新增：能力评分项的类型
export interface AbilityScore {
  name: string;
  score: number;
}

// 【核心修正】定义完整的、精确的报告内容类型
export interface InterviewReport {
  overall_score: number;
  overall_comment: string;
  ability_scores: AbilityScore[]; // 使用上面的 AbilityScore 类型
  strength_analysis: string;
  weakness_analysis: string;
  improvement_suggestions: string[];
}

// --- API 函数 ---
export const getInterviewHistoryApi = (): Promise<InterviewSessionItem[]> => {
  return request({ url: '/interviews/', method: 'get' });
};

export const getInterviewReportApi = (sessionId: string): Promise<InterviewReport> => {
  return request({ url: `/interviews/${sessionId}/finish/`, method: 'post' });
};