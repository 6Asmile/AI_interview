// src/api/modules/chat.ts (新建文件)

import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';
import type { UserProfile } from './user';

// --- 类型定义 ---

export interface Message {
  id: number;
  sender: UserProfile;
  content: string;
  message_type: 'text' | 'image' | 'file' | 'voice' | 'video';
  file_url: string | null;
  timestamp: string;
  is_read: boolean;
}

export interface Conversation {
  id: number;
  participants: UserProfile[];
  updated_at: string;
  latest_message: Message | null;
  unread_count: number;
}


// --- API 函数 ---

/**
 * 获取当前用户的所有对话列表
 */
export const getConversationsApi = (): Promise<Conversation[]> => {
  // 聊天列表通常不分页，一次性加载
  return request({
    url: '/conversations/',
    method: 'get',
  });
};

/**
 * 获取指定对话的历史消息 (分页)
 * @param conversationId - 对话的 ID
 * @param params - 分页参数, e.g., { page: 1 }
 */
export const getMessagesApi = (conversationId: number, params?: any): Promise<PaginatedResponse<Message>> => {
  return request({
    url: `/conversations/${conversationId}/messages/`,
    method: 'get',
    params,
  });
};
export const startConversationApi = (userId: number): Promise<Conversation> => {
  return request({
    url: `/conversations/start_with/${userId}/`,
    method: 'post',
  });
};