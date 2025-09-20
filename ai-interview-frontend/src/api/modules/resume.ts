// src/api/modules/resume.ts
import request from '@/api/request';

export interface ResumeItem {
  id: number;
  user: number;
  title: string;
  file: string; // 后端 FileField 会返回文件的 URL 字符串
  file_type: string;
  file_size: number;
  is_default: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  parsed_content: string;
}

// API: 获取简历列表
export const getResumeListApi = (): Promise<ResumeItem[]> => {
  return request({
    url: '/resumes/',
    method: 'get',
  });
};

// 【核心改造】
// API: 创建简历 (现在接收一个 FormData 对象)
export const createResumeApi = (formData: FormData): Promise<ResumeItem> => {
  return request({
    url: '/resumes/',
    method: 'post',
    data: formData,
    // 必须重写 headers 为 multipart/form-data
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

// API: 删除简历
export const deleteResumeApi = (id: number) => {
  return request({
    url: `/resumes/${id}/`,
    method: 'delete',
  });
};