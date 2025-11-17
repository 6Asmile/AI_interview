// src/store/modules/chat.ts (完整代码)

import { defineStore } from 'pinia';
import { getConversationsApi, getMessagesApi, startConversationApi } from '@/api/modules/chat';
import type { Conversation, Message } from '@/api/modules/chat';
import { ElMessage } from 'element-plus';
import { useAuthStore } from './auth';

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
        this.conversations = await getConversationsApi();
      } catch (error) {
        ElMessage.error('无法加载对话列表');
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
    connectWebSocket() {
      // 先关闭任何已存在的连接
      if (this.socket) {
        this.socket.close();
      }
      if (!this.activeConversation) return;

      const authStore = useAuthStore();
      const currentUser = authStore.user;
      if (!currentUser) return;

      // 从当前激活的对话中找到对方用户
      const otherUser = this.activeConversation.participants.find(p => p.id !== currentUser.id);
      if (!otherUser) return;

      this.connectionStatus = 'connecting';
      const protocol = window.location.protocol === 'https' ? 'wss' : 'ws';
      const wsUrl = `${protocol}://${window.location.host}/ws/chat/${otherUser.id}/`;

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.connectionStatus = 'connected';
        console.log('Chat WebSocket connected to user:', otherUser.id);
      };

      this.socket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // 处理收到的新聊天消息
        if (data.type === 'chat_message') {
          const newMessage = data.message as Message;
          if (this.activeConversationId) {
             if (!this.messages[this.activeConversationId]) {
                this.messages[this.activeConversationId] = [];
             }
             // 将新消息插入到数组的最前面（因为后端是按时间倒序返回的）
             this.messages[this.activeConversationId].unshift(newMessage);
          }
          // 更新对话列表中的“最新消息”预览和时间戳
          const conv = this.activeConversation;
          if (conv) {
             conv.latest_message = newMessage;
             conv.updated_at = newMessage.timestamp;
             // 如果收到消息的不是自己，增加未读数
             if (newMessage.sender.id !== currentUser.id) {
                 conv.unread_count++;
             }
          }
        // 处理“对方正在输入”状态
        } else if (data.type === 'typing_indicator') {
          this.otherUserTypingStatus = data.is_typing;
        }
      };

      this.socket.onclose = () => {
        this.connectionStatus = 'disconnected';
        console.log('Chat WebSocket disconnected.');
      };
      
      this.socket.onerror = (error) => {
        this.connectionStatus = 'error';
        console.error('Chat WebSocket error:', error);
        ElMessage.error('聊天连接发生错误');
      };
    },

    /**
     * 通过 WebSocket 发送消息
     * @param messageData 消息内容对象
     */
    sendMessage(messageData: { content: string; message_type: string; file_url?: string }) {
      if (this.socket && this.connectionStatus === 'connected') {
        this.socket.send(JSON.stringify({
          type: 'chat_message',
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