// src/api/modules/system.ts
import request from '@/api/request';

// 定义AI设置的数据类型
export interface AISettingsData {
  ai_model: string;
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
export const updateAISettingsApi = (data: AISettingsData): Promise<AISettingsData> => {
  // 使用 PATCH 方法，这样可以只更新部分字段
  return request({
    url: '/settings/ai/',
    method: 'patch', 
    data,
  });
};