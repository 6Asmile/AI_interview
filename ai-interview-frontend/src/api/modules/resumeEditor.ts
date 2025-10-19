// src/api/modules/resumeEditor.ts
import request from '@/api/request';
// 【核心修改】从 resume.ts 导入类型
import type { StructuredResume, EducationItem, WorkExperienceItem, ProjectExperienceItem, SkillItem } from './resume';

// 【核心修改】导出从 resume.ts 导入的类型，方便 store 使用
export type { StructuredResume, EducationItem, WorkExperienceItem, ProjectExperienceItem, SkillItem };


// --- 统一的 CRUD API 辅助函数 ---
const createApiEndpoints = <T>(resource: string) => ({
  list: (resumeId: number): Promise<T[]> => request({ url: `/resumes/${resumeId}/${resource}/`, method: 'get' }),
  create: (resumeId: number, data: T): Promise<T> => request({ url: `/resumes/${resumeId}/${resource}/`, method: 'post', data }),
  update: (resumeId: number, id: number, data: Partial<T>): Promise<T> => request({ url: `/resumes/${resumeId}/${resource}/${id}/`, method: 'patch', data }),
  destroy: (resumeId: number, id: number): Promise<void> => request({ url: `/resumes/${resumeId}/${resource}/${id}/`, method: 'delete' }),
});

// --- 为每个模块创建具体的 API 端点 ---
export const educationApi = createApiEndpoints<EducationItem>('educations');
export const workExperienceApi = createApiEndpoints<WorkExperienceItem>('work_experiences');
export const projectExperienceApi = createApiEndpoints<ProjectExperienceItem>('project_experiences');
export const skillApi = createApiEndpoints<SkillItem>('skills');

// API: 获取单个（结构化）简历的完整详情
export const getStructuredResumeApi = (resumeId: number): Promise<StructuredResume> => {
    return request({
        url: `/resumes/${resumeId}/`,
        method: 'get',
    });
};
// 【核心新增】AI 润色 API 函数
export const polishDescriptionApi = (html_content: string, job_position?: string): Promise<{ polished_html: string }> => {
  return request({
    url: '/polish-description/',
    method: 'post',
    data: {
      html_content,
      job_position,
    },
  });
};

// 定义分析报告的类型结构，以便获得完整的 TypeScript 类型提示
export interface AnalysisReport {
  overall_score: number;
  keyword_analysis: {
    jd_keywords: string[];
    matched_keywords: string[];
    missing_keywords: string[];
  };
  strengths_analysis: string[];
  weaknesses_analysis: string[];
  suggestions: {
    module: string;
    suggestion: string;
  }[];
}

// 【核心新增】AI 简历分析 API 函数
export const analyzeResumeApi = (resume_id: number, jd_text: string): Promise<AnalysisReport> => {
  return request({
    url: '/analyze-resume/',
    method: 'post',
    data: {
      resume_id,
      jd_text,
    },
  });
};