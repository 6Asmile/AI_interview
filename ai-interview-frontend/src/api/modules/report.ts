import request from '@/api/request';
import type { InterviewSessionItem } from './interview';

// --- 类型定义 ---
export interface AbilityScore {
  name: string;
  score: number;
}

// 新增：关键词分析的类型
export interface KeywordAnalysis {
  matched_keywords: string[];
  missing_keywords: string[];
  analysis_comment: string;
}

// 新增：STAR法则分析的类型
export interface StarAnalysisItem {
  question_sequence: number;
  is_behavioral_question: boolean;
  conforms_to_star: boolean;
  star_feedback: string;
}

// 【核心改造】终极的、完整的报告内容类型
export interface InterviewReport {
  overall_score: number;
  overall_comment: string;
  ability_scores: AbilityScore[];
  strength_analysis: string;
  weakness_analysis: string;
  improvement_suggestions: string[];
  keyword_analysis: KeywordAnalysis; // 新增
  star_analysis: StarAnalysisItem[]; // 新增
}

// --- API 函数 (保持不变) ---
export const getInterviewHistoryApi = (): Promise<InterviewSessionItem[]> => {
  return request({ url: '/interviews/', method: 'get' });
};

export const getInterviewReportApi = (sessionId: string): Promise<InterviewReport> => {
  return request({ url: `/interviews/${sessionId}/finish/`, method: 'post' });
};