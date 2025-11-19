<!-- src/components/chat/ConversationList.vue -->
<template>
  <div class="h-full flex flex-col">
    <div class="p-4 border-b font-semibold text-lg">对话列表</div>
    <el-scrollbar class="flex-grow">
      <div v-if="conversations && conversations.length > 0">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="p-4 flex items-center cursor-pointer hover:bg-gray-100"
          :class="{ 'bg-blue-50': conv.id === activeId }"
          @click="selectConv(conv.id)"
        >
          <!-- 使用计算属性或方法来获取显示信息，避免在模板中做复杂逻辑 -->
          <el-avatar :src="getAvatar(conv)">
            {{ getInitials(conv) }}
          </el-avatar>
          <div class="ml-3 flex-grow overflow-hidden">
            <div class="flex justify-between items-center">
              <span class="font-semibold truncate">{{ getName(conv) }}</span>
              <span class="text-xs text-gray-400">{{ formatTime(conv.updated_at) }}</span>
            </div>
            <div class="text-sm text-gray-500 truncate mt-1">
              {{ conv.latest_message?.content || '...' }}
            </div>
          </div>
          <el-badge :value="conv.unread_count" :hidden="!conv.unread_count" class="ml-2" />
        </div>
      </div>
      
      <div v-else class="p-4 text-center text-gray-400">
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