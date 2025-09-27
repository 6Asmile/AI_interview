// src/api/modules/resume.ts
import request from '@/api/request';

// --- 【核心修改】将所有简历相关的类型定义集中在此 ---

export interface EducationItem { id?: number; school: string; degree: string; major: string; start_date: string; end_date: string; }
export interface WorkExperienceItem { id?: number; company: string; position: string; start_date: string; end_date: string | null; description: string; }
export interface ProjectExperienceItem { id?: number; project_name: string; role: string; start_date: string; end_date: string | null; description: string; }
export interface SkillItem { id?: number; skill_name: string; proficiency: string; }

// 基础简历类型
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
   file_url?: string; // 【新增】添加 file_url 字段
}

// 扩展后的结构化简历类型
export interface StructuredResume extends ResumeItem {
    educations: EducationItem[];
    work_experiences: WorkExperienceItem[];
    project_experiences: ProjectExperienceItem[];
    skills: SkillItem[];
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

// 【核心修改】更新简历 API，使其接受并返回完整的结构化简历类型
export const updateResumeApi = (id: number, data: Partial<StructuredResume>): Promise<StructuredResume> => {
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