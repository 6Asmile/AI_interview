import request from '@/api/request';

const v2Base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/api\/v1\/?$/, '/api/v2');
const v2 = (config: any) => request({ ...config, baseURL: v2Base });

export interface CareerFact {
  id: number;
  fact_type: 'summary' | 'education' | 'work' | 'project' | 'skill' | 'certification' | 'achievement' | 'open_source';
  title: string;
  organization: string;
  role: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  skills: string[];
  metrics: Record<string, string | number>;
  source_type: 'manual' | 'resume_import' | 'github' | 'interview';
  source_url: string;
  verification_status: 'draft' | 'confirmed' | 'rejected';
  updated_at: string;
}

export interface JobTarget {
  id: number;
  company_name: string;
  position_name: string;
  jd_text: string;
  source_url: string;
  location: string;
  deadline: string | null;
  keywords: string[];
  status: 'active' | 'archived';
  application_count: number;
  updated_at: string;
}

export type ApplicationStatus = 'saved' | 'applied' | 'screening' | 'interview' | 'offer' | 'accepted' | 'rejected' | 'withdrawn';

export interface JobApplication {
  id: number;
  job_target: number;
  job_target_detail: JobTarget;
  resume_version: number | null;
  resume_version_number: number | null;
  cover_letter: string;
  status: ApplicationStatus;
  source: string;
  next_action_at: string | null;
  notes: string;
  updated_at: string;
}

export interface LearningTask {
  id: number;
  title: string;
  dimension: string;
  priority: 'high' | 'medium' | 'low';
  status: 'todo' | 'doing' | 'done';
  due_at: string | null;
}

export interface CareerDashboard {
  pipeline: Record<ApplicationStatus, number>;
  active_job_targets: number;
  confirmed_facts: number;
  resume_count: number;
  resumes_without_versions: number;
  open_learning_tasks: number;
  upcoming_actions: Array<{ application_id: number; company_name: string; position_name: string; next_action_at: string; status: ApplicationStatus }>;
}

const results = <T>(response: any): T[] => Array.isArray(response) ? response : (response?.results || []);

export const getCareerDashboardApi = (): Promise<CareerDashboard> => v2({ url: '/career-dashboard/', method: 'get' });
export const getCareerFactsApi = async (): Promise<CareerFact[]> => results<CareerFact>(await v2({ url: '/career-facts/', method: 'get' }));
export const createCareerFactApi = (data: Partial<CareerFact>): Promise<CareerFact> => v2({ url: '/career-facts/', method: 'post', data });
export const updateCareerFactApi = (id: number, data: Partial<CareerFact>): Promise<CareerFact> => v2({ url: `/career-facts/${id}/`, method: 'patch', data });
export const deleteCareerFactApi = (id: number) => v2({ url: `/career-facts/${id}/`, method: 'delete' });
export const confirmCareerFactApi = (id: number): Promise<CareerFact> => v2({ url: `/career-facts/${id}/confirm/`, method: 'post' });

export const getJobTargetsApi = async (): Promise<JobTarget[]> => results<JobTarget>(await v2({ url: '/job-targets/', method: 'get' }));
export const createJobTargetApi = (data: Partial<JobTarget>): Promise<JobTarget> => v2({ url: '/job-targets/', method: 'post', data });
export const updateJobTargetApi = (id: number, data: Partial<JobTarget>): Promise<JobTarget> => v2({ url: `/job-targets/${id}/`, method: 'patch', data });
export const deleteJobTargetApi = (id: number) => v2({ url: `/job-targets/${id}/`, method: 'delete' });

export const getApplicationsApi = async (): Promise<JobApplication[]> => results<JobApplication>(await v2({ url: '/applications/', method: 'get' }));
export const createApplicationApi = (data: Partial<JobApplication>): Promise<JobApplication> => v2({ url: '/applications/', method: 'post', data });
export const updateApplicationApi = (id: number, data: Partial<JobApplication>): Promise<JobApplication> => v2({ url: `/applications/${id}/`, method: 'patch', data });
export const deleteApplicationApi = (id: number) => v2({ url: `/applications/${id}/`, method: 'delete' });

export const getLearningTasksApi = async (): Promise<LearningTask[]> => results<LearningTask>(await v2({ url: '/learning-tasks/', method: 'get' }));
export const updateLearningTaskApi = (id: number, data: Partial<LearningTask>): Promise<LearningTask> => v2({ url: `/learning-tasks/${id}/`, method: 'patch', data });
