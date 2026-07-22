import request from '@/api/request';

export type WebSocketTicketScope = 'chat' | 'interview_speech';

export interface WebSocketTicket {
  ticket: string;
  scope: WebSocketTicketScope;
  resource_id: string;
  expires_at: string;
}

export const createWebSocketTicketApi = (scope: WebSocketTicketScope, resourceId: string | number): Promise<WebSocketTicket> => request({
  url: '/ws-tickets/',
  method: 'post',
  data: { scope, resource_id: String(resourceId) },
});

export const resolveWebSocketBase = () => {
  const configured = (import.meta.env.VITE_WS_URL || '').replace(/\/$/, '');
  if (configured) return configured;
  const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/api\/v1\/?$/, '').replace(/\/$/, '');
  if (apiBase && /^https?:\/\//.test(apiBase)) return apiBase.replace(/^http/, 'ws');
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
};
