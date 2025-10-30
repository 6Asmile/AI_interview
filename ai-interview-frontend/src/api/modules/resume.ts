// src/api/modules/resume.ts
import request from '@/api/request';
import { ResumeLayout } from '@/store/modules/resumeEditor';
// 【核心修改】导入通用分页类型
import type { PaginatedResponse } from '@/types/api';

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
  // file_type: string; // 根据后端序列化器，这些字段可能不再需要
  // file_size: number;
  is_default: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  parsed_content: string;
  file_url?: string;
  
   // 【核心修复】使用联合类型，允许 content_json 是数组(旧)或对象(新)
  content_json: ResumeLayout | any[] | null;

    // 【核心修复】新增 template_name 字段
  template_name?: string;
  // 在线简历字段 (暂时保留用于兼容)
  full_name?: string;
  phone?: string;
  email?: string;
  job_title?: string;
  city?: string;
  summary?: string;
}

// 扩展后的结构化简历类型 (现在继承自更新后的 ResumeItem)
export interface StructuredResume extends ResumeItem {
    educations: EducationItem[];
    work_experiences: WorkExperienceItem[];
    project_experiences: ProjectExperienceItem[];
    skills: SkillItem[];
}


// --- API 函数 ---

// 【核心修复】为函数添加 params 参数
export const getResumeListApi = (params?: any): Promise<PaginatedResponse<ResumeItem>> => {
  return request({
    url: '/resumes/',
    method: 'get',
    params, // <-- 确保 params 被传递
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

// 【核心修改】更新简历 API，使其接受并返回完整的简历类型
// 注意：现在我们用 ResumeItem 因为它包含了所有字段
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