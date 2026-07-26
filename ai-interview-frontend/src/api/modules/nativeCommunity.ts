import request from '@/api/request';

const v2Base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/api\/v1\/?$/, '/api/v2');
const v2 = (config: any) => request({ ...config, baseURL: v2Base });

export const getCommunityFeedApi = (params?: Record<string, unknown>) =>
  v2({ url: '/community/feed/', method: 'get', params });

export const getCommunityContentsApi = (params?: Record<string, unknown>) =>
  v2({ url: '/community/contents/', method: 'get', params });

export const createCommunityContentApi = (data: Record<string, unknown>) =>
  v2({ url: '/community/contents/', method: 'post', data });

export const publishCommunityContentApi = (id: string) =>
  v2({
    url: `/community/contents/${id}/publish/`,
    method: 'post',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });

export const commentCommunityContentApi = (id: string, data: Record<string, unknown>) =>
  v2({ url: `/community/contents/${id}/comments/`, method: 'post', data });

export const reactCommunityContentApi = (id: string, kind = 'like') =>
  v2({ url: `/community/contents/${id}/reactions/`, method: 'post', data: { kind } });

export const reportCommunityContentApi = (id: string, data: Record<string, unknown>) =>
  v2({ url: `/community/contents/${id}/reports/`, method: 'post', data });
