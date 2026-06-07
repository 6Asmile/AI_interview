<!-- src/components/chat/ConversationList.vue -->
<template>
  <div class="conversation-shell">
    <div class="conversation-header">
      <div>
        <p class="conversation-kicker">Inbox</p>
        <h2>对话列表</h2>
      </div>
      <span class="conversation-count">{{ conversations.length }}</span>
    </div>
    <el-scrollbar class="conversation-scroll">
      <div v-if="conversations && conversations.length > 0">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: conv.id === activeId }"
          @click="selectConv(conv.id)"
        >
          <!-- 使用计算属性或方法来获取显示信息，避免在模板中做复杂逻辑 -->
          <el-avatar :src="getAvatar(conv)" :size="46" class="conversation-avatar">
            {{ getInitials(conv) }}
          </el-avatar>
          <div class="conversation-content">
            <div class="conversation-meta">
              <span class="conversation-name">{{ getName(conv) }}</span>
              <span class="conversation-time">{{ formatTime(conv.updated_at) }}</span>
            </div>
            <div class="conversation-preview">
              {{ conv.latest_message?.content || '...' }}
            </div>
          </div>
          <el-badge :value="conv.unread_count" :hidden="!conv.unread_count" class="conversation-badge" />
        </div>
      </div>
      
      <div v-else class="conversation-empty">
        暂无对话
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useChatStore } from '@/store/modules/chat';
import { useAuthStore } from '@/store/modules/auth';
import type { Conversation } from '@/api/modules/chat';
import { formatDateTime } from '@/utils/format';

const chatStore = useChatStore();
const authStore = useAuthStore();

// 使用计算属性从 store 获取数据，保持响应性
const conversations = computed(() => chatStore.conversations);
const activeId = computed(() => chatStore.activeConversationId);
const currentUserId = computed(() => authStore.user?.id);

// 辅助函数：安全地获取对方用户
const getOtherParticipant = (conv: Conversation) => {
  if (!conv || !conv.participants || !currentUserId.value) return null;
  return conv.participants.find(p => p.id !== currentUserId.value);
};

// 获取头像 URL
const getAvatar = (conv: Conversation) => {
  const user = getOtherParticipant(conv);
  return user?.avatar || undefined;
};

// 获取首字母
const getInitials = (conv: Conversation) => {
  const user = getOtherParticipant(conv);
  return (user?.username || '?').charAt(0).toUpperCase();
};

// 获取用户名
const getName = (conv: Conversation) => {
  const user = getOtherParticipant(conv);
  return user?.username || '未知用户';
};

const formatTime = (time: string) => {
  return formatDateTime(time, 'MM-DD HH:mm');
};

const selectConv = (id: number) => {
  chatStore.selectConversation(id);
};

onMounted(() => {
  chatStore.fetchConversations();
});
</script>

<style scoped>
.conversation-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.conversation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid #e6edf8;
}

.conversation-kicker {
  margin: 0 0 6px;
  color: #6781b0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.conversation-header h2 {
  margin: 0;
  color: #1f3153;
  font-size: 22px;
}

.conversation-count {
  min-width: 34px;
  height: 34px;
  padding: 0 10px;
  border-radius: 999px;
  background: #eaf2ff;
  color: #3f67b0;
  font-size: 13px;
  font-weight: 700;
  line-height: 34px;
  text-align: center;
}

.conversation-scroll {
  flex: 1;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 10px 12px;
  padding: 14px;
  border: 1px solid transparent;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.22s ease;
}

.conversation-item:hover {
  border-color: #dbe7fb;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 14px 24px rgba(66, 99, 156, 0.08);
}

.conversation-item.active {
  border-color: #9ab9f4;
  background: linear-gradient(135deg, #edf4ff 0%, #ffffff 100%);
  box-shadow: 0 16px 28px rgba(64, 123, 255, 0.12);
}

.conversation-avatar {
  flex-shrink: 0;
  box-shadow: 0 10px 20px rgba(72, 102, 153, 0.14);
}

.conversation-content {
  min-width: 0;
  flex: 1;
}

.conversation-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.conversation-name {
  overflow: hidden;
  color: #203252;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-time {
  flex-shrink: 0;
  color: #9aa7ba;
  font-size: 12px;
}

.conversation-preview {
  margin-top: 6px;
  overflow: hidden;
  color: #6f7f98;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-badge {
  margin-left: 4px;
}

.conversation-empty {
  padding: 40px 16px;
  color: #99a6bb;
  text-align: center;
}
</style>
