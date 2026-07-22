// src/store/modules/chat.ts (完整代码)

import { defineStore } from 'pinia';
import { getConversationsApi, getMessagesApi, startConversationApi } from '@/api/modules/chat';
import type { Conversation, Message } from '@/api/modules/chat';
import { ElMessage } from 'element-plus';
import { useAuthStore } from './auth';
import { v4 as uuidv4 } from 'uuid';
import { createWebSocketTicketApi, resolveWebSocketBase } from '@/api/modules/realtime';

interface ChatState {
  conversations: Conversation[];
  activeConversationId: number | null;
  messages: { [key: number]: Message[] }; // 按对话ID缓存消息，值为消息数组
  socket: WebSocket | null;
  connectionStatus: 'disconnected' | 'connecting' | 'connected' | 'error';
  otherUserTypingStatus: boolean;
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    conversations: [],
    activeConversationId: null,
    messages: {},
    socket: null,
    connectionStatus: 'disconnected',
    otherUserTypingStatus: false,
  }),

  getters: {
    activeConversation(state): Conversation | undefined {
      return state.conversations.find(c => c.id === state.activeConversationId);
    },
    activeMessages(state): Message[] {
      if (!state.activeConversationId) return [];
      // 我们的消息是 unshift 进来的（新消息在最前），为了正确显示，需要 reverse
      return (state.messages[state.activeConversationId] || []).slice().reverse();
    }
  },

  actions: {
    /**
     * 获取当前用户的所有对话列表
     */
    async fetchConversations() {
      try {
        const response: any = await getConversationsApi();
        
        // 检查后端返回的是否是分页结构
        if (response.results && Array.isArray(response.results)) {
          // 如果是分页数据，取 results 字段
          this.conversations = response.results;
        } else if (Array.isArray(response)) {
          // 如果后端没开启分页，直接取响应
          this.conversations = response;
        } else {
          // 防御性代码：如果数据格式不对，重置为空数组
          this.conversations = [];
          console.error("对话列表数据格式错误:", response);
        }
      } catch (error) {
        ElMessage.error('无法加载对话列表');
        this.conversations = []; // 出错时确保是空数组
      }
    },

    /**
     * 选中一个已存在的对话
     * @param conversationId 对话ID
     */
    async selectConversation(conversationId: number) {
      if (this.activeConversationId === conversationId) return;

      this.activeConversationId = conversationId;
      this.otherUserTypingStatus = false;

      // 如果这个对话的历史消息从未被加载过，则去加载第一页
      if (!this.messages[conversationId]) {
        try {
          const response = await getMessagesApi(conversationId, { page: 1 });
          this.messages[conversationId] = response.results;
        } catch (error) {
          ElMessage.error('加载历史消息失败');
        }
      }
      
      // 建立或切换 WebSocket 连接
      this.connectWebSocket();
    },
    
    /**
     * [核心] 根据用户ID发起一个新对话或选择一个现有对话
     * @param userId 对方用户的ID
     */
    async startAndSelectConversation(userId: number) {
      try {
        // 1. 调用后端API来获取或创建对话
        const newOrExistingConv = await startConversationApi(userId);

        // 2. 更新本地的对话列表状态
        const index = this.conversations.findIndex(c => c.id === newOrExistingConv.id);
        if (index > -1) {
          // 如果对话已存在于列表中，则用后端返回的最新数据替换它
          this.conversations[index] = newOrExistingConv;
        } else {
          // 如果是全新的对话，则添加到列表的最前面
          this.conversations.unshift(newOrExistingConv);
        }

        // 3. 选中这个对话，这将自动触发加载历史消息和连接WebSocket
        await this.selectConversation(newOrExistingConv.id);
        
        return newOrExistingConv.id;
      } catch (error) {
        ElMessage.error('无法开启对话，您可能无法与自己聊天。');
        return null;
      }
    },

    /**
     * 建立 WebSocket 连接
     */
    async connectWebSocket() {
      // 1. 清理旧连接
      if (this.socket) {
        this.socket.close();
      }
      if (!this.activeConversation) return;

      const authStore = useAuthStore();
      const currentUser = authStore.user;
      if (!currentUser) return;

      // 2. 找到聊天对象
      const otherUser = this.activeConversation.participants.find(p => p.id !== currentUser.id);
      if (!otherUser) return;

      this.connectionStatus = 'connecting';

      let ticket;
      try {
        ticket = await createWebSocketTicketApi('chat', otherUser.id);
      } catch {
        this.connectionStatus = 'error';
        return;
      }
      if (!this.activeConversation || !this.activeConversation.participants.some(item => item.id === otherUser.id)) return;
      const wsUrl = `${resolveWebSocketBase()}/ws/chat/${otherUser.id}/?ticket=${encodeURIComponent(ticket.ticket)}`;
      this.socket = new WebSocket(wsUrl);

      // 4. 事件监听
      this.socket.onopen = () => {
        this.connectionStatus = 'connected';
        this.socket?.send(JSON.stringify({ type: 'read_messages' }));
      };

      this.socket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // 处理收到的新聊天消息
        if (data.type === 'chat_message') {
          const newMessage = data.message as Message;
          
          // --- 【核心修复】强制触发 UI 更新 ---
          // 1. 更新右侧消息列表
          if (this.activeConversationId) {
             if (!this.messages[this.activeConversationId]) {
                this.messages[this.activeConversationId] = [];
             }
             const current = this.messages[this.activeConversationId];
             const existingIndex = current.findIndex(item => item.id === newMessage.id || item.client_message_id === newMessage.client_message_id);
             if (existingIndex >= 0) current.splice(existingIndex, 1);
             this.messages[this.activeConversationId] = [newMessage, ...current];
          }

          // 2. 更新左侧对话列表预览
          const convIndex = this.conversations.findIndex(c => c.id === this.activeConversationId);
          
          if (convIndex !== -1) {
             const conv = this.conversations[convIndex];
             
             // 更新最新消息预览
             conv.latest_message = newMessage;
             conv.updated_at = newMessage.timestamp;
             
             // 如果是对方发来的，增加未读计数
             if (newMessage.sender.id !== currentUser.id) {
                 conv.unread_count = (conv.unread_count || 0) + 1;
             }

             // 3. 将当前对话置顶
             this.conversations.splice(convIndex, 1);
             this.conversations.unshift(conv);
          }

        // 处理“对方正在输入”状态
        } else if (data.type === 'typing_indicator') {
          this.otherUserTypingStatus = data.is_typing;
        } else if (data.type === 'read_receipt' && this.activeConversationId) {
          const lastReadId = Number(data.last_read_message_id || 0);
          this.messages[this.activeConversationId] = (this.messages[this.activeConversationId] || []).map(message =>
            message.id <= lastReadId ? { ...message, is_read: true, delivery_status: 'read' } : message
          );
        } else if (data.type === 'error') {
          ElMessage.error(data.message || '消息发送失败');
        }
      };

      this.socket.onclose = () => {
        this.connectionStatus = 'disconnected';
      };
      
      this.socket.onerror = (error) => {
        this.connectionStatus = 'error';
        console.error('Chat WebSocket error:', error);
        // ElMessage.error('聊天连接发生错误'); // 可以根据需要决定是否弹窗
      };
    },

    /**
     * 通过 WebSocket 发送消息
     * @param messageData 消息内容对象
     */
    sendMessage(messageData: { content: string; message_type: string; attachment_id?: number; reply_to_id?: number }) {
      if (this.socket && this.connectionStatus === 'connected') {
        this.socket.send(JSON.stringify({
          type: 'chat_message',
          client_message_id: uuidv4(),
          ...messageData,
        }));
      } else {
        ElMessage.error('聊天未连接，无法发送消息');
      }
    },
    
    /**
     * 发送“正在输入”的指示器状态
     * @param isTyping 是否正在输入
     */
    sendTypingIndicator(isTyping: boolean) {
        if (this.socket && this.connectionStatus === 'connected') {
            this.socket.send(JSON.stringify({
                type: 'typing_indicator',
                is_typing: isTyping,
            }));
        }
    },
    
    /**
     * 断开 WebSocket 连接并清理状态
     */
    disconnect() {
      if (this.socket) {
        this.socket.close();
        this.socket = null;
      }
      this.activeConversationId = null;
      this.connectionStatus = 'disconnected';
      this.otherUserTypingStatus = false;
      // 注意：这里我们不清除 messages 和 conversations，以便用户下次进入时能看到缓存
    }
  },
});
