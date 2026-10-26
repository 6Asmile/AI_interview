// src/api/modules/resume.ts
import request from '@/api/request';
// 【核心修改】导入通用分页类型
import type { PaginatedResponse } from '@/types/api';

export interface LegacyResumeComponent {
  id: string;
  componentName: string;
  moduleType: string;
  title: string;
  props: Record<string, any>;
  styles: Record<string, any>;
}
export interface ResumeLayout { sidebar: LegacyResumeComponent[]; main: LegacyResumeComponent[]; }

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

// Resume Intelligence V2. New Studio code uses these contracts exclusively;
// legacy functions above remain for the two-release compatibility window.
export interface JsonResume {
  basics: Record<string, any>;
  work: Array<Record<string, any>>;
  volunteer: Array<Record<string, any>>;
  education: Array<Record<string, any>>;
  awards: Array<Record<string, any>>;
  certificates: Array<Record<string, any>>;
  publications: Array<Record<string, any>>;
  skills: Array<Record<string, any>>;
  languages: Array<Record<string, any>>;
  interests: Array<Record<string, any>>;
  references: Array<Record<string, any>>;
  projects: Array<Record<string, any>>;
  meta: Record<string, any>;
  'x-ifaceoff': Record<string, any>;
}

export interface ResumeDesign {
  template_key: string;
  template_version: string;
  page_size: 'A4' | 'Letter';
  language: 'zh-CN' | 'en-US';
  font: string;
  color: string;
  density: 'compact' | 'balanced' | 'comfortable';
  date_format: string;
  show_avatar: boolean;
  section_order: string[];
  hidden_sections: string[];
}

export interface ResumeVersionV2 {
  id: number;
  version_number: number;
  parent: number | null;
  schema_version: string;
  content_hash: string;
  language: string;
  resume_json: JsonResume;
  source: string;
  change_summary: string;
  created_at: string;
  evidence_links: Array<Record<string, any>>;
}

export interface ResumeDesignRevision {
  id: number;
  revision_number: number;
  template_key: string;
  template_version: string;
  language: string;
  page_size: string;
  design_json: ResumeDesign;
  design_hash: string;
  created_at: string;
}

export interface ResumeV2 {
  id: number;
  title: string;
  status: 'draft' | 'ready' | 'archived';
  is_default: boolean;
  canonical_schema_version: string;
  current_version: ResumeVersionV2;
  current_design_revision: ResumeDesignRevision;
  draft_etag: string;
  created_at: string;
  updated_at: string;
}

export interface ResumeDraft {
  id: number;
  base_version: number;
  base_version_number: number;
  resume_json: JsonResume;
  design_json: ResumeDesign;
  revision: number;
  etag: string;
  created_at: string;
  updated_at: string;
}

export interface ResumeTemplate {
  key: string;
  version: string;
  name: Record<string, string>;
  description: string;
  default_font: string;
  default_color: string;
  default_density: string;
  capabilities: Record<string, any>;
  thumbnail: string;
  use_tags: string[];
  industry_tags: string[];
  role_tags: string[];
}

export interface AsyncOperationAccepted {
  operation_id: string;
  status: 'accepted';
  events_url: string;
  result_url: string;
  artifact_id?: string;
  quality_report_id?: number;
  resume_id?: number;
  import_job_id?: number;
  etag?: string;
}

export interface ResumeArtifact {
  id: string;
  resume: number;
  content_version: number | null;
  content_version_number: number | null;
  design_revision: number | null;
  design_revision_number: number | null;
  draft_etag: string;
  format: 'preview' | 'pdf' | 'png' | 'docx' | 'json' | 'markdown';
  status: 'pending' | 'processing' | 'ready' | 'failed';
  renderer_name: string;
  renderer_version: string;
  page_count: number;
  file_url: string | null;
  error_code: string;
  error_message: string;
}

export interface ResumeQualityReport {
  id: number;
  status: string;
  score: number;
  report_json: Record<string, any>;
  error_message: string;
  created_at: string;
}

export interface ResumeShareLink {
  id: number;
  token_hint: string;
  field_policy: Record<string, boolean>;
  expires_at: string | null;
  revoked_at: string | null;
  is_revoked: boolean;
  allow_download: boolean;
  download_limit: number | null;
  download_count: number;
  token?: string;
  share_url?: string;
}

export interface ResumeSuggestionV2 {
  id: number;
  base_version: number;
  task_key: string;
  job_target: number | null;
  patch: Array<Record<string, any>>;
  summary: string;
  rationale: string;
  evidence_fact_ids: number[];
  evidence_links: Array<Record<string, any>>;
  status: 'pending' | 'accepted' | 'rejected';
  accepted_version: number | null;
  variant_id: number | null;
  created_at: string;
}

export interface ResumeVariantV2 {
  id: number;
  resume: number;
  source_version: number;
  source_version_number: number;
  version: number;
  version_number: number;
  job_target: number;
  company_name: string;
  position_name: string;
  title: string;
  created_at: string;
}

const configuredApiBase = String(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
const v2Base = /\/api\/v\d+$/.test(configuredApiBase)
  ? configuredApiBase.replace(/\/api\/v\d+$/, '/api/v2')
  : configuredApiBase.endsWith('/api')
    ? `${configuredApiBase}/v2`
    : `${configuredApiBase}/api/v2`;
const v2 = (config: any) => request({ ...config, baseURL: v2Base });
const idempotencyKey = () => crypto.randomUUID();
const asList = <T>(response: any): T[] => Array.isArray(response) ? response : (response?.results || []);

export const getResumesV2Api = async (): Promise<ResumeV2[]> => asList<ResumeV2>(
  await v2({ url: '/resumes/', method: 'get' }),
);
export const getResumeV2Api = (id: number): Promise<ResumeV2> => v2({ url: `/resumes/${id}/`, method: 'get' });
export const createResumeV2Api = (data: { title: string; status?: string; is_default?: boolean }): Promise<ResumeV2> =>
  v2({ url: '/resumes/', method: 'post', data });
export const updateResumeV2Api = (id: number, data: Partial<Pick<ResumeV2, 'title' | 'status' | 'is_default'>>): Promise<ResumeV2> =>
  v2({ url: `/resumes/${id}/`, method: 'patch', data });
export const deleteResumeV2Api = (id: number) => v2({ url: `/resumes/${id}/`, method: 'delete' });
export const getResumeDraftApi = (id: number): Promise<ResumeDraft> => v2({ url: `/resumes/${id}/draft/`, method: 'get' });
export const patchResumeDraftApi = (id: number, etag: string, data: Partial<Pick<ResumeDraft, 'resume_json' | 'design_json'>>): Promise<ResumeDraft> =>
  v2({ url: `/resumes/${id}/draft/`, method: 'patch', data, headers: { 'If-Match': `"${etag}"` } });
export const getResumeAvatarApi = (id: number): Promise<{ avatar: { id: number; url: string; checksum_sha256: string } | null }> =>
  v2({ url: `/resumes/${id}/avatar/`, method: 'get' });
export const uploadResumeAvatarApi = (
  id: number,
  etag: string,
  file: File,
): Promise<{ avatar: { id: number; url: string; checksum_sha256: string }; etag: string }> => {
  const data = new FormData();
  data.append('file', file);
  return v2({
    url: `/resumes/${id}/avatar/`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', 'If-Match': `"${etag}"` },
  });
};
export const deleteResumeAvatarApi = (id: number, etag: string): Promise<{ avatar: null; etag: string }> =>
  v2({ url: `/resumes/${id}/avatar/`, method: 'delete', headers: { 'If-Match': `"${etag}"` } });
export const commitResumeDraftApi = (id: number, etag: string, change_summary: string): Promise<ResumeVersionV2> =>
  v2({ url: `/resumes/${id}/versions/`, method: 'post', data: { change_summary }, headers: { 'If-Match': `"${etag}"` } });
export const getResumeVersionsV2Api = async (id: number): Promise<ResumeVersionV2[]> => asList<ResumeVersionV2>(
  await v2({ url: `/resumes/${id}/versions/`, method: 'get' }),
);
export const getResumeVersionDiffApi = (resumeId: number, versionId: number, against?: number) =>
  v2({ url: `/resumes/${resumeId}/versions/${versionId}/diff/`, method: 'get', params: against ? { against } : undefined });
export const getResumeTemplatesApi = (): Promise<{ schema_version: string; templates: ResumeTemplate[] }> =>
  v2({ url: '/resume-templates/', method: 'get' });
export const requestResumePreviewApi = (id: number): Promise<AsyncOperationAccepted> =>
  v2({ url: `/resumes/${id}/preview/`, method: 'post', data: {}, headers: { 'Idempotency-Key': idempotencyKey() } });
export const requestResumeExportApi = (id: number, format: 'pdf' | 'png' | 'docx' | 'json' | 'markdown', version_id?: number): Promise<AsyncOperationAccepted> =>
  v2({ url: `/resumes/${id}/exports/`, method: 'post', data: { format, version_id }, headers: { 'Idempotency-Key': idempotencyKey() } });
export const getResumeArtifactApi = (id: string): Promise<ResumeArtifact> =>
  v2({ url: `/resume-artifacts/${id}/`, method: 'get', suppressErrorToast: true } as any);
export const requestResumeQualityApi = (id: number, version_id?: number): Promise<AsyncOperationAccepted> =>
  v2({ url: `/resumes/${id}/quality-reports/`, method: 'post', data: { version_id }, headers: { 'Idempotency-Key': idempotencyKey() } });
export const getResumeQualityReportsApi = async (id: number): Promise<ResumeQualityReport[]> => asList<ResumeQualityReport>(
  await v2({ url: `/resumes/${id}/quality-reports/`, method: 'get' }),
);
export const getResumeShareLinksApi = async (id: number): Promise<ResumeShareLink[]> => asList<ResumeShareLink>(
  await v2({ url: `/resumes/${id}/share-links/`, method: 'get' }),
);
export const createResumeShareLinkApi = (id: number, data: Record<string, any>): Promise<ResumeShareLink> =>
  v2({ url: `/resumes/${id}/share-links/`, method: 'post', data });
export const revokeResumeShareLinkApi = (resumeId: number, shareId: number): Promise<ResumeShareLink> =>
  v2({ url: `/resumes/${resumeId}/share-links/${shareId}/revoke/`, method: 'post', data: {} });
export const getResumeSuggestionsV2Api = async (id: number): Promise<ResumeSuggestionV2[]> => asList<ResumeSuggestionV2>(
  await v2({ url: `/resumes/${id}/suggestions/`, method: 'get' }),
);
export const requestResumeSuggestionApi = (
  id: number,
  data: { task_key: string; instruction?: string; job_target_id?: number | null; base_version_id?: number },
): Promise<AsyncOperationAccepted> => v2({
  url: `/resumes/${id}/suggestions/`,
  method: 'post',
  data,
  headers: { 'Idempotency-Key': idempotencyKey() },
});
export const acceptResumeSuggestionApi = (resumeId: number, suggestionId: number): Promise<ResumeVersionV2> =>
  v2({ url: `/resumes/${resumeId}/suggestions/${suggestionId}/accept/`, method: 'post', data: {} });
export const rejectResumeSuggestionApi = (resumeId: number, suggestionId: number): Promise<ResumeSuggestionV2> =>
  v2({ url: `/resumes/${resumeId}/suggestions/${suggestionId}/reject/`, method: 'post', data: {} });
export const getResumeVariantsApi = async (resumeId: number): Promise<ResumeVariantV2[]> => asList<ResumeVariantV2>(
  await v2({ url: `/resumes/${resumeId}/variants/`, method: 'get' }),
);
export const getAsyncOperationApi = (id: string): Promise<Record<string, any>> =>
  v2({ url: `/operations/${id}/`, method: 'get', suppressErrorToast: true } as any);
export const importResumeV2Api = (data: FormData): Promise<AsyncOperationAccepted> =>
  v2({
    url: '/resume-imports/',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', 'Idempotency-Key': idempotencyKey() },
  });
export const getPublicResumeShareApi = (token: string, password = ''): Promise<{
  title: string;
  version: number;
  resume_json: JsonResume;
  design: ResumeDesign;
  allow_download: boolean;
  expires_at: string | null;
}> => v2({
  url: `/resume-shares/${encodeURIComponent(token)}/`,
  method: 'get',
  headers: password ? { 'X-Resume-Share-Password': password } : undefined,
  _authRetry: true,
  suppressErrorToast: true,
} as any);
