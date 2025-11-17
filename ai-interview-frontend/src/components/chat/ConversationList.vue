<!-- src/components/chat/ConversationList.vue (新建文件) -->
<template>
  <div class="h-full flex flex-col">
    <div class="p-4 border-b font-semibold text-lg">对话列表</div>
    <el-scrollbar class="flex-grow">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.id"
        class="p-4 flex items-center cursor-pointer hover:bg-gray-100"
        :class="{ 'bg-blue-50': conv.id === chatStore.activeConversationId }"
        @click="chatStore.selectConversation(conv.id)"
      >
        <el-avatar :src="getOtherParticipant(conv)?.avatar || undefined">
          {{ getOtherParticipant(conv)?.username.charAt(0) }}
        </el-avatar>
        <div class="ml-3 flex-grow overflow-hidden">
          <div class="flex justify-between items-center">
            <span class="font-semibold truncate">{{ getOtherParticipant(conv)?.username }}</span>
            <span class="text-xs text-gray-400">{{ formatDateTime(conv.updated_at, 'MM-DD HH:mm') }}</span>
          </div>
          <div class="text-sm text-gray-500 truncate mt-1">
            {{ conv.latest_message?.content || '...' }}
          </div>
        </div>
        <el-badge :value="conv.unread_count" :hidden="conv.unread_count === 0" class="ml-2" />
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useChatStore } from '@/store/modules/chat';
import { useAuthStore } from '@/store/modules/auth';
import type { Conversation } from '@/api/modules/chat';
import type { UserProfile } from '@/api/modules/user';
import { formatDateTime } from '@/utils/format';

const chatStore = useChatStore();
const authStore = useAuthStore();

const getOtherParticipant = (conv: Conversation): UserProfile | undefined => {
  return conv.participants.find(p => p.id !== authStore.user?.id);
};

onMounted(() => {
  chatStore.fetchConversations();
});
</script>