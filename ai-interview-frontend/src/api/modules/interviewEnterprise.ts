import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';

export interface RubricDimension {
  id?: number;
  key: string;
  name: string;
  description?: string;
  weight: string | number;
  min_coverage: number;
  order: number;
  rule_config?: Record<string, any>;
}

export interface InterviewRubric {
  id: number;
  name: string;
  description: string;
  version: number;
  visibility: 'system' | 'shared' | 'private';
  is_active: boolean;
  dimensions: RubricDimension[];
  can_edit: boolean;
}

export interface InterviewTemplateStage {
  id?: number;
  stage_key: string;
  name: string;
  order: number;
  question_ratio: string | number;
  target_dimensions: string[];
  question_guidance: string;
}

export interface InterviewTemplate {
  id: number;
  name: string;
  description: string;
  job_keywords: string[];
  rubric: number;
  rubric_detail?: InterviewRubric;
  visibility: 'system' | 'shared' | 'private';
  is_active: boolean;
  version: number;
  require_rag: boolean;
  config: Record<string, any>;
  stages: InterviewTemplateStage[];
  can_edit: boolean;
}

export interface EvaluationCase {
  id?: number;
  job_position: string;
  jd_text?: string;
  resume_text?: string;
  question: string;
  answer: string;
  contexts?: any[];
  expected_dimensions?: string[];
  expected_follow_up?: string;
  ground_truth?: string;
}

export interface EvaluationDataset {
  id: number;
  name: string;
  description: string;
  visibility: 'shared' | 'private';
  cases: EvaluationCase[];
  can_edit: boolean;
}

export interface EvaluationRun {
  id: number;
  dataset: number;
  template?: number | null;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  summary: Record<string, any>;
  error_message: string;
  metrics: Array<{ id: number; metric_name: string; score: number | null; detail: Record<string, any> }>;
  created_at: string;
}

export const getInterviewTemplatesApi = (): Promise<PaginatedResponse<InterviewTemplate>> => request({
  url: '/interview-templates/',
  method: 'get',
});

export const createInterviewTemplateApi = (data: Partial<InterviewTemplate>): Promise<InterviewTemplate> => request({
  url: '/interview-templates/',
  method: 'post',
  data,
});

export const updateInterviewTemplateApi = (id: number, data: Partial<InterviewTemplate>): Promise<InterviewTemplate> => request({
  url: `/interview-templates/${id}/`,
  method: 'patch',
  data,
});

export const cloneInterviewTemplateApi = (id: number): Promise<InterviewTemplate> => request({
  url: `/interview-templates/${id}/clone/`,
  method: 'post',
});

export const getInterviewRubricsApi = (): Promise<PaginatedResponse<InterviewRubric>> => request({
  url: '/interview-rubrics/',
  method: 'get',
});

export const createEvaluationDatasetApi = (data: Partial<EvaluationDataset>): Promise<EvaluationDataset> => request({
  url: '/evaluation-datasets/',
  method: 'post',
  data,
});

export const getEvaluationDatasetsApi = (): Promise<PaginatedResponse<EvaluationDataset>> => request({
  url: '/evaluation-datasets/',
  method: 'get',
});

export const createEvaluationRunApi = (data: { dataset: number; template?: number | null }): Promise<EvaluationRun> => request({
  url: '/evaluation-runs/',
  method: 'post',
  data,
});

export const getEvaluationRunsApi = (): Promise<PaginatedResponse<EvaluationRun>> => request({
  url: '/evaluation-runs/',
  method: 'get',
});
