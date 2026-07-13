// src/api/modules/chat.ts (新建文件)

import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';
import type { UserProfile } from './user';

// --- 类型定义 ---

export interface Message {
  id: number;
  client_message_id: string;
  sender: UserProfile;
  content: string;
  message_type: 'text' | 'image' | 'file' | 'voice' | 'video';
  file_url: string | null;
  delivery_status: 'pending' | 'sent' | 'delivered' | 'read' | 'failed';
  reply_to: number | null;
  edited_at: string | null;
  revoked_at: string | null;
  attachments: ChatAttachment[];
  timestamp: string;
  is_read: boolean;
}

export interface ChatAttachment {
  id: number;
  original_name: string;
  mime_type: string;
  size: number;
  scan_status: string;
  scan_engine: string;
  file_url: string;
}

export interface Conversation {
  id: number;
  conversation_type: 'user_dm' | 'application' | 'interview_support';
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

export const uploadChatAttachmentApi = (file: File): Promise<ChatAttachment> => {
  const data = new FormData();
  data.append('file', file);
  return request({ url: '/chat/attachments/', method: 'post', data, headers: { 'Content-Type': 'multipart/form-data' } });
};

export const markConversationReadApi = (conversationId: number) => request({ url: `/conversations/${conversationId}/mark-read/`, method: 'post' });
