import request from '@/api/request';

export type AsyncTaskStatus =
  | 'pending'
  | 'claimed'
  | 'running'
  | 'retrying'
  | 'review_required'
  | 'cancel_requested'
  | 'succeeded'
  | 'failed'
  | 'canceled';

export interface AsyncTaskItem {
  id: string;
  operation_type: string;
  title: string;
  status: AsyncTaskStatus;
  progress: number;
  error_code: string;
  error_message: string;
  retryable: boolean;
  can_retry: boolean;
  can_cancel: boolean;
  metadata: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AsyncTaskList {
  count: number;
  results: AsyncTaskItem[];
}

export const getTasksApi = (params?: Record<string, string>): Promise<AsyncTaskList> =>
  request({ url: '/tasks/', method: 'get', params });

export const retryTaskApi = (id: string): Promise<AsyncTaskItem> =>
  request({
    url: `/tasks/${id}/retry/`, method: 'post',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });

export const cancelTaskApi = (id: string): Promise<AsyncTaskItem> =>
  request({
    url: `/tasks/${id}/cancel/`, method: 'post',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
