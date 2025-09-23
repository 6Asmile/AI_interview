import request from '@/api/request';

// --- AI 设置相关 (保持不变) ---
// --- AI 模型相关 (新增) ---
export interface AIModelItem {
  id: number;
  name: string;
  model_slug: string;
  description: string;
}

// API: 获取所有可用的 AI 模型
export const getAIModelsApi = (): Promise<AIModelItem[]> => {
  return request({
    url: '/ai-models/',
    method: 'get',
  });
};

// --- AI 设置相关 (改造) ---

// AISettingsData 现在包含一个嵌套的 AIModelItem 对象
export interface AISettingsData {
  ai_model: AIModelItem | null; // 模型可以是 null
  ai_model_id: number | null; // 用于发送更新
  api_key: string;
}

// 定义更新时发送的数据类型
export interface UpdateAISettingsData {
    ai_model_id: number | null;
    api_key: string;
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

// 更新 API 函数，指向新的 URL 并返回新的数据类型
export const getJobsByIndustryApi = (): Promise<IndustryWithJobsItem[]> => {
  return request({
    url: '/jobs-by-industry/',
    method: 'get',
  });
};