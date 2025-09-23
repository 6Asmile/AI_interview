import request from '@/api/request';

// --- 类型定义 ---
export interface ResumeItem {
  id: number;
  user: number;
  title: string;
  file: string | null;
  file_type: string;
  file_size: number;
  is_default: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  parsed_content: string;
  // 在线简历字段
  full_name?: string;
  phone?: string;
  email?: string;
  job_title?: string;
  city?: string;
  summary?: string;
}

// --- API 函数 ---

// 获取简历列表
export const getResumeListApi = (): Promise<ResumeItem[]> => {
  return request({
    url: '/resumes/',
    method: 'get',
  });
};

// 创建简历 (同时支持在线创建和文件上传创建)
export const createResumeApi = (formData: FormData | { title: string, status: string }): Promise<ResumeItem> => {
  if (formData instanceof FormData) {
    // 文件上传
    return request({
      url: '/resumes/',
      method: 'post',
      data: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  } else {
    // 在线创建
    return request({
      url: '/resumes/',
      method: 'post',
      data: formData,
    });
  }
};

// 【核心修正】新增更新简历主信息的 API
export const updateResumeApi = (id: number, data: Partial<ResumeItem>): Promise<ResumeItem> => {
    return request({
        url: `/resumes/${id}/`,
        method: 'patch', // 使用 patch 更新部分字段
        data,
    });
};


// 删除简历
export const deleteResumeApi = (id: number) => {
  return request({
    url: `/resumes/${id}/`,
    method: 'delete',
  });
};