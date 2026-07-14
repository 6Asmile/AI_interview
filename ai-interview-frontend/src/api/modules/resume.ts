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
  canonical_schema_version?: string;
  current_version?: ResumeVersion | null;
  version_count?: number;
  latest_import_job?: ResumeImportJob | null;
  import_job?: ResumeImportJob | null;
}

export interface ResumeVersion {
  id: number;
  resume: number;
  version_number: number;
  parent: number | null;
  schema_version: string;
  resume_json: Record<string, any>;
  layout_json: Record<string, any>;
  evidence_snapshot: Array<Record<string, any>>;
  source: string;
  change_summary: string;
  created_at: string;
}

export interface ResumeImportJob {
  id: number;
  resume: number;
  status: 'pending' | 'processing' | 'review_required' | 'confirmed' | 'failed' | 'canceled';
  parser_name: string;
  parser_version: string;
  parser_fallback_reason: string;
  parsed_json: Record<string, any>;
  error_message: string;
  updated_at: string;
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

export const getResumeVersionsApi = (id: number): Promise<ResumeVersion[]> => request({ url: `/resumes/${id}/versions/`, method: 'get' });
export const restoreResumeVersionApi = (resumeId: number, versionId: number): Promise<ResumeVersion> => request({ url: `/resumes/${resumeId}/versions/${versionId}/restore/`, method: 'post' });
export const getResumeImportsApi = async (): Promise<ResumeImportJob[]> => { const response: any = await request({ url: '/resume-imports/', method: 'get' }); return Array.isArray(response) ? response : (response.results || []); };
export const getResumeImportApi = (jobId: number): Promise<ResumeImportJob> => request({ url: `/resume-imports/${jobId}/`, method: 'get' });
export const confirmResumeImportApi = (jobId: number, resume_json?: Record<string, any>): Promise<ResumeVersion> => request({ url: `/resume-imports/${jobId}/confirm/`, method: 'post', data: resume_json ? { resume_json } : {} });
export const retryResumeImportApi = (jobId: number): Promise<ResumeImportJob> => request({ url: `/resume-imports/${jobId}/retry/`, method: 'post' });
export const getResumeFitScoreApi = (resumeId: number, jd_text: string) => request({ url: `/resumes/${resumeId}/fit-score/`, method: 'post', data: { jd_text } });
