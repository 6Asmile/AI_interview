import request from '@/api/request';
// 【核心修改】导入通用分页类型
import type { PaginatedResponse } from '@/types/api';

// --- AI 设置相关 (保持不变) ---
// --- AI 模型相关 (新增) ---
export interface AIModelItem {
  id: number;
  name: string;
  model_slug: string;
  description: string;
}

// 【核心修改】更新 getAIModelsApi 的返回类型
export const getAIModelsApi = (): Promise<PaginatedResponse<AIModelItem>> => {
  return request({
    url: '/ai-models/',
    method: 'get',
  });
};

// --- AI 设置相关 (改造) ---

// AISettingsData 现在代表整个设置对象
export interface AISettingsData {
  ai_model: AIModelItem | null; // 用户的默认模型
  api_keys: Record<string, string>; // 用户的 Key 映射, e.g., { '1': 'key-abc', '3': 'key-xyz' }
}

// 定义更新时发送的数据类型
export interface UpdateAISettingsData {
    ai_model_id?: number | null; // 设为可选
    api_keys?: Record<string, string>; // 设为可选
}


// API: 获取当前用户的AI设置
export const getAISettingsApi = (): Promise<AISettingsData> => {
  return request({
    url: '/settings/ai/',
    method: 'get',
  });
};

// API: 更新当前用户的AI设置
export const updateAISettingsApi = (data: UpdateAISettingsData): Promise<AISettingsData> => {
  return request({
    url: '/settings/ai/',
    method: 'patch', 
    data,
  });
};

// --- 【核心改造】岗位管理相关 ---

// 单个岗位的数据类型 (保持不变)
export interface JobPositionItem {
  id: number;
  name: string;
  description: string;
  icon_svg: string;
}

// 新增：单个行业及其下岗位列表的数据类型
export interface IndustryWithJobsItem {
  id: number;
  name: string;
  description: string;
  job_positions: JobPositionItem[]; // 嵌套岗位列表
}

// 【核心修改】更新 getJobsByIndustryApi 的返回类型，因为它现在也受全局分页影响
// 虽然我们可能不需要它的分页功能，但类型必须正确
export const getJobsByIndustryApi = (): Promise<PaginatedResponse<IndustryWithJobsItem>> => {
  return request({
    url: '/jobs-by-industry/',
    method: 'get',
  });
};