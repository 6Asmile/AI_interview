import request from '@/api/request';

// --- AI 设置相关 (保持不变) ---
export interface AISettingsData {
  ai_model: string;
  api_key: string;
}
export const getAISettingsApi = (): Promise<AISettingsData> => {
  return request({ url: '/settings/ai/', method: 'get' });
};
export const updateAISettingsApi = (data: AISettingsData): Promise<AISettingsData> => {
  return request({ url: '/settings/ai/', method: 'patch', data });
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

// 更新 API 函数，指向新的 URL 并返回新的数据类型
export const getJobsByIndustryApi = (): Promise<IndustryWithJobsItem[]> => {
  return request({
    url: '/jobs-by-industry/',
    method: 'get',
  });
};