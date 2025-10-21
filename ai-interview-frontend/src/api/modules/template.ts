import request from '@/api/request';

// 定义从后端接收的模板数据类型
export interface ResumeTemplateItem {
  id: number;
  name: string;
  slug: string;
  preview_image: string; // URL
  structure_json: any; // 前端编辑器可用的 JSON 结构
  description: string;
}

// API: 获取所有简历模板
export const getResumeTemplatesApi = (): Promise<ResumeTemplateItem[]> => {
  return request({
    url: '/resume-templates/',
    method: 'get',
  });
};