import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';

// 定义单个通知项的数据结构，需要足够灵活以处理通用外键
export interface NotificationItem {
  id: number;
  verb: string;
  is_read: boolean;
  timestamp: string;
  actor: { id: number; username: string; avatar: string | null; };
  target?: any; // target 可以是文章、评论等任何对象
  action_object?: any;
}

// 获取通知列表
export const getNotificationsApi = (params?: any): Promise<PaginatedResponse<NotificationItem>> => {
  return request({ url: '/notifications/', method: 'get', params });
};

// 将所有通知标记为已读
export const markAllNotificationsAsReadApi = (): Promise<void> => {
  return request({ url: '/notifications/mark-all-as-read/', method: 'post' });
};

// 将单条通知标记为已读
export const markNotificationAsReadApi = (id: number): Promise<void> => {
  return request({ url: `/notifications/${id}/mark-as-read/`, method: 'post' });
};