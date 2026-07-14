import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';

export type KnowledgeVisibility = 'private' | 'public';
export type KnowledgeStatus = 'draft' | 'indexing' | 'indexed' | 'failed';
export type KnowledgeApprovalStatus = 'draft' | 'pending_review' | 'approved' | 'rejected' | 'archived';
export type KnowledgeParseStatus = 'pending' | 'parsing' | 'parsed' | 'failed';
export type KnowledgeDifficulty = 'any' | 'easy' | 'medium' | 'hard';
export type KnowledgeImportStatus = 'pending' | 'processing' | 'completed' | 'partial_failed' | 'failed';

export interface KnowledgeChunk {
  id: string;
  chunk_index: number;
  parent_chunk?: string | null;
  chunk_level?: number;
  heading_path?: string[];
  page_start?: number | null;
  page_end?: number | null;
  block_type?: string;
  token_count?: number;
  content_hash?: string;
  semantic_group_id?: string;
  content: string;
  metadata?: Record<string, any>;
  embedding_model?: string;
  indexed_at?: string | null;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  content: string;
  source_type: string;
  source_file?: string | null;
  source_file_url?: string;
  file_type?: string;
  parse_status: KnowledgeParseStatus;
  parser_name: string;
  parser_version: string;
  parser_fallback_reason: string;
  parsed_content?: Record<string, any>;
  ocr_enabled: boolean;
  draft_revision?: string | null;
  published_revision?: string | null;
  visibility: KnowledgeVisibility;
  job_positions: string[];
  ability_tags: string[];
  difficulty: KnowledgeDifficulty;
  status: KnowledgeStatus;
  approval_status: KnowledgeApprovalStatus;
  chunk_count: number;
  last_indexed_at: string | null;
  last_retrieved_at: string | null;
  retrieval_count: number;
  error_message: string;
  rejection_reason: string;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by: number | null;
  approved_by_username?: string;
  import_batch?: string | null;
  import_batch_id?: string | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
  can_submit_review: boolean;
  can_approve: boolean;
  chunks?: KnowledgeChunk[];
}

export interface KnowledgeChunkDraft {
  id: string;
  revision: string;
  parent?: string | null;
  order: number;
  block_type: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  content: string;
  table_data: any[];
  metadata: Record<string, any>;
  token_count: number;
  content_hash: string;
  is_excluded: boolean;
  updated_at: string;
}

export interface KnowledgeDocumentRevision {
  id: string;
  document: string;
  version_number: number;
  status: 'draft' | 'pending_review' | 'approved' | 'published' | 'rejected' | 'superseded';
  parser_snapshot: Record<string, any>;
  rejection_reason: string;
  chunk_count: number;
  submitted_at: string | null;
  approved_at: string | null;
  published_at: string | null;
  created_at: string;
}

export interface KnowledgeImportFileItem {
  id: string;
  original_name: string;
  status: 'pending' | 'processing' | 'imported' | 'failed';
  error_message: string;
  document_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeImportBatch {
  id: string;
  status: KnowledgeImportStatus;
  uploaded_by: number | null;
  source_files: string[];
  options?: Record<string, any>;
  total_files: number;
  success_count: number;
  failed_count: number;
  error_log: Array<{ file: string; error: string }>;
  import_files: KnowledgeImportFileItem[];
  documents?: KnowledgeDocument[];
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocumentPayload {
  title: string;
  content: string;
  source_type?: string;
  visibility?: KnowledgeVisibility;
  job_positions?: string[];
  ability_tags?: string[];
  difficulty?: KnowledgeDifficulty;
  auto_index?: boolean;
}

export interface KnowledgeDocumentQuery {
  page?: number;
  page_size?: number;
  search?: string;
  visibility?: KnowledgeVisibility | '';
  status?: KnowledgeStatus | '';
  approval_status?: KnowledgeApprovalStatus | '';
  difficulty?: KnowledgeDifficulty | '';
  source_type?: string;
  job_position?: string;
  ability_tag?: string;
}

export interface KnowledgeChunkPreviewItem {
  chunk_index: number;
  parent_index?: number;
  child_index?: number;
  block_type?: string;
  heading_path?: string[];
  page_start?: number | null;
  page_end?: number | null;
  token_count?: number;
  content: string;
  length: number;
}

export interface KnowledgeChunkPreviewParent {
  parent_index: number;
  block_type: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  token_count?: number;
  content: string;
  child_count: number;
  children: KnowledgeChunkPreviewItem[];
}

export interface KnowledgeChunkPreviewResponse {
  strategy?: string;
  parent_count: number;
  chunk_count: number;
  parents: KnowledgeChunkPreviewParent[];
  chunks: KnowledgeChunkPreviewItem[];
}

export const getKnowledgeDocumentsApi = (
  params?: KnowledgeDocumentQuery
): Promise<PaginatedResponse<KnowledgeDocument> | KnowledgeDocument[]> => {
  return request({
    url: '/knowledge/documents/',
    method: 'get',
    params,
  });
};

export const createKnowledgeDocumentApi = (
  data: KnowledgeDocumentPayload
): Promise<KnowledgeDocument> => {
  return request({
    url: '/knowledge/documents/',
    method: 'post',
    data,
  });
};

export const updateKnowledgeDocumentApi = (
  id: string,
  data: Partial<KnowledgeDocumentPayload>
): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/`,
    method: 'patch',
    data,
  });
};

export const getKnowledgeRevisionsApi = (id: string): Promise<KnowledgeDocumentRevision[]> => request({
  url: `/knowledge/documents/${id}/revisions/`, method: 'get',
});
export const getKnowledgeChunkDraftsApi = (id: string): Promise<KnowledgeChunkDraft[]> => request({
  url: `/knowledge/documents/${id}/chunk-drafts/`, method: 'get',
});
export const updateKnowledgeChunkDraftApi = (
  documentId: string,
  chunkId: string,
  data: Partial<Pick<KnowledgeChunkDraft, 'content' | 'block_type' | 'heading_path' | 'is_excluded' | 'metadata' | 'table_data'>>,
): Promise<KnowledgeChunkDraft> => request({
  url: `/knowledge/documents/${documentId}/chunk-drafts/${chunkId}/`, method: 'patch', data,
});
export const deleteKnowledgeChunkDraftApi = (documentId: string, chunkId: string): Promise<void> => request({
  url: `/knowledge/documents/${documentId}/chunk-drafts/${chunkId}/`, method: 'delete',
});
export const reorderKnowledgeChunkDraftsApi = (documentId: string, chunkIds: string[]): Promise<KnowledgeChunkDraft[]> => request({
  url: `/knowledge/documents/${documentId}/chunk-drafts/reorder/`, method: 'post', data: { chunk_ids: chunkIds },
});
export const mergeKnowledgeChunkDraftsApi = (documentId: string, chunkIds: string[]): Promise<KnowledgeChunkDraft> => request({
  url: `/knowledge/documents/${documentId}/chunk-drafts/merge/`, method: 'post', data: { chunk_ids: chunkIds },
});
export const splitKnowledgeChunkDraftApi = (documentId: string, chunkId: string, splitAt: number): Promise<KnowledgeChunkDraft[]> => request({
  url: `/knowledge/documents/${documentId}/chunk-drafts/${chunkId}/split/`, method: 'post', data: { split_at: splitAt },
});

export const deleteKnowledgeDocumentApi = (id: string): Promise<void> => {
  return request({
    url: `/knowledge/documents/${id}/`,
    method: 'delete',
  });
};

export const reindexKnowledgeDocumentApi = (
  id: string
): Promise<KnowledgeDocument | { message: string; document_id: string; status: KnowledgeStatus }> => {
  return request({
    url: `/knowledge/documents/${id}/reindex/`,
    method: 'post',
  });
};

export const submitKnowledgeDocumentReviewApi = (id: string): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/submit-review/`,
    method: 'post',
  });
};

export const approveKnowledgeDocumentApi = (id: string): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/approve/`,
    method: 'post',
  });
};

export const rejectKnowledgeDocumentApi = (
  id: string,
  rejection_reason: string
): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/reject/`,
    method: 'post',
    data: { rejection_reason },
  });
};

export const archiveKnowledgeDocumentApi = (id: string): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/archive/`,
    method: 'post',
  });
};

export const importKnowledgeBatchApi = (data: FormData): Promise<KnowledgeImportBatch> => {
  return request({
    url: '/knowledge/import-batches/',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const getKnowledgeImportBatchesApi = (
  params?: { page?: number; page_size?: number }
): Promise<PaginatedResponse<KnowledgeImportBatch> | KnowledgeImportBatch[]> => {
  return request({
    url: '/knowledge/import-batches/',
    method: 'get',
    params,
  });
};

export const retryKnowledgeImportBatchApi = (id: string): Promise<KnowledgeImportBatch> => {
  return request({
    url: `/knowledge/import-batches/${id}/retry-failed/`,
    method: 'post',
  });
};

export const reparseKnowledgeDocumentApi = (id: string): Promise<KnowledgeDocument> => {
  return request({
    url: `/knowledge/documents/${id}/reparse/`,
    method: 'post',
  });
};

export const previewStructuredKnowledgeChunksApi = (
  id: string
): Promise<KnowledgeChunkPreviewResponse> => {
  return request({
    url: `/knowledge/documents/${id}/preview-structured-chunks/`,
    method: 'post',
  });
};

export const debugKnowledgeSearchApi = (data: Record<string, any>): Promise<{
  contexts: any[];
  retrieval_trace: Record<string, any>;
  retrieval_explanation?: Record<string, any>;
}> => {
  return request({
    url: '/knowledge/search/debug/',
    method: 'post',
    data,
  });
};

export const previewKnowledgeChunksApi = (data: {
  title?: string;
  content: string;
  chunk_size?: number;
  overlap?: number;
}): Promise<KnowledgeChunkPreviewResponse> => {
  return request({
    url: '/knowledge/documents/preview-chunks/',
    method: 'post',
    data,
  });
};
