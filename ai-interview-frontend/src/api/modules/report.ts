import request from '@/api/request';
import type { AnalysisReport } from './resumeEditor'; // 导入类型
import type { InterviewSessionItem, AnalysisFrame } from './interview'; // 【新增】导入 AnalysisFrame
// 【核心修改】导入通用分页类型
import type { PaginatedResponse } from '@/types/api';
// --- 类型定义 ---
export interface AbilityScore {
  name: string;
  score: number;
}


// 【核心改造】在报告类型中加入情绪分析数据
export interface InterviewReport {
  overall_score: number;
  overall_comment: string;
  ability_scores: AbilityScore[];
  strength_analysis: string;
  weakness_analysis: string;
  improvement_suggestions: string[];
  keyword_analysis: KeywordAnalysis;
  star_analysis: StarAnalysisItem[];
  // 【新增】情绪分析的时间序列数据
  emotion_analysis: AnalysisFrame[];
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
// 【核心修复】为函数添加 params 参数
export const getInterviewHistoryApi = (params?: any): Promise<PaginatedResponse<InterviewSessionItem>> => {
  return request({ url: '/interviews/', method: 'get', params });
};

export const getInterviewReportApi = (sessionId: string): Promise<InterviewReport> => {
  return request({ url: `/interviews/${sessionId}/finish/`, method: 'post' });
};

// 定义完整的报告模型类型
export interface ResumeAnalysisReportItem {
    id: string;
    user: number;
    resume: number;
    jd_text: string;
    report_data: AnalysisReport;
    overall_score: number;
    created_at: string;
}

// 【核心修复】为函数添加 params 参数
export const getAnalysisHistoryApi = (params?: any): Promise<PaginatedResponse<ResumeAnalysisReportItem>> => {
    return request({ url: '/analysis-reports/', method: 'get', params });
};


// 获取单个分析报告详情
export const getAnalysisReportDetailApi = (reportId: string): Promise<ResumeAnalysisReportItem> => {
    return request({ url: `/analysis-reports/${reportId}/`, method: 'get' });
};