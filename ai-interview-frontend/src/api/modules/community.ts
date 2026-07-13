import request from '@/api/request';

export interface CommunityStatus { configured: boolean; community_url: string; identity: null | { discourse_user_id: number; username: string; trust_level: number; reputation: number; synced_at: string }; }
export const getCommunityStatusApi = (): Promise<CommunityStatus> => request({ url: '/community/me/', method: 'get' });
export const searchCommunityApi = (q: string) => request({ url: '/community/search/', method: 'get', params: { q, limit: 30 } });

