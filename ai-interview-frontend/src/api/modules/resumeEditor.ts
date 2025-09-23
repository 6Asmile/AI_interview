import request from '@/api/request';
import type { ResumeItem } from './resume'; // 我们将复用并扩展这个类型

// --- 类型定义 ---
export interface EducationItem { id?: number; school: string; degree: string; major: string; start_date: string; end_date: string; }
export interface WorkExperienceItem { id?: number; company: string; position: string; start_date: string; end_date: string | null; description: string; }
export interface ProjectExperienceItem { id?: number; project_name: string; role: string; start_date: string; end_date: string | null; description: string; }
export interface SkillItem { id?: number; skill_name: string; proficiency: string; }

// 扩展 ResumeItem，使其包含结构化数据
export interface StructuredResume extends ResumeItem {
    educations: EducationItem[];
    work_experiences: WorkExperienceItem[];
    project_experiences: ProjectExperienceItem[];
    skills: SkillItem[];
}

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