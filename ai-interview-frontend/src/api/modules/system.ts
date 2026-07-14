import request from '@/api/request';

export interface SystemReadiness {
  ok: boolean;
  async_jobs_available: boolean;
  components: Record<string, { ok: boolean; critical: boolean; reason?: string; latency_ms?: number }>;
}

export const getSystemReadinessApi = (): Promise<SystemReadiness> => request({ url: '/system/readiness/', method: 'get' });
// 【核心修改】导入通用分页类型
import type { PaginatedResponse } from '@/types/api';

// --- AI 设置相关 (保持不变) ---
// --- AI 模型相关 (新增) ---
export interface AIModelItem {
  id: number;
  name: string;
  model_slug: string;
  base_url: string;
  provider: string;
  model_type: 'chat' | 'embedding' | 'rerank' | 'asr' | 'tts';
  description: string;
  supports_json_mode: boolean;
  dimension?: number | null;
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
  chat_model: AIModelItem | null;
  embedding_model: AIModelItem | null;
  rerank_model: AIModelItem | null;
  asr_model: AIModelItem | null;
  tts_model: AIModelItem | null;
  api_keys: Record<string, string>; // 用户的 Key 映射, e.g., { '1': 'key-abc', '3': 'key-xyz' }
}

export interface AIModelGatewayHealthResult {
  ok: boolean;
  model_type: AIModelItem['model_type'];
  config: {
    provider: string;
    model_slug: string;
    model_type: string;
    base_url: string;
    key_source: string;
    has_api_key: boolean;
    api_key_masked?: string;
  };
  latency_ms: number | null;
  error?: string;
  dimension?: number;
  note?: string;
}

// 定义更新时发送的数据类型
export interface UpdateAISettingsData {
    ai_model_id?: number | null; // 设为可选
    chat_model_id?: number | null;
    embedding_model_id?: number | null;
    rerank_model_id?: number | null;
    asr_model_id?: number | null;
    tts_model_id?: number | null;
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

export const checkAIModelGatewayHealthApi = (
  model_type: AIModelItem['model_type']
): Promise<AIModelGatewayHealthResult> => {
  return request({
    url: '/settings/ai/health/',
    method: 'post',
    data: { model_type },
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
