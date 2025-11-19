<!-- src/components/chat/ChatWindow.vue -->
<template>
  <div v-if="activeConversation" class="h-full flex flex-col">
    <!-- Header -->
    <div class="p-4 border-b flex items-center justify-between">
      <span class="font-semibold text-lg">
        {{ getOtherParticipant(activeConversation)?.username || '对话中...' }}
      </span>
    </div>

    <!-- Message Area -->
    <el-scrollbar ref="scrollbarRef" class="flex-grow p-4 bg-gray-50">
      <MessageItem
        v-for="message in chatStore.activeMessages"
        :key="message.id"
        :message="message"
      />
       <div v-if="chatStore.otherUserTypingStatus" class="flex justify-start">
        <div class="bg-gray-200 text-gray-600 p-2 rounded-lg text-sm">
          对方正在输入...
        </div>
      </div>
    </el-scrollbar>

    <!-- Input Area -->
    <MessageInput />
  </div>
  <div v-else class="h-full flex items-center justify-center text-gray-400">
    选择一个对话开始聊天
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue';
import { useChatStore } from '@/store/modules/chat';
import { useAuthStore } from '@/store/modules/auth';
import type { Conversation } from '@/api/modules/chat';
import type { UserProfile } from '@/api/modules/user';
import MessageItem from './MessageItem.vue';
import MessageInput from './MessageInput.vue';
import type { ElScrollbar } from 'element-plus';

const chatStore = useChatStore();
const authStore = useAuthStore();
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();

const activeConversation = computed(() => chatStore.activeConversation);

// 【核心修复】与 ConversationList 保持一致的安全逻辑
const getOtherParticipant = (conv: Conversation): UserProfile | undefined => {
  if (!authStore.user || !authStore.user.id || !conv || !conv.participants) {
    return undefined;
  }
  return conv.participants.find(p => p.id !== authStore.user?.id);
};

watch(() => chatStore.activeMessages.length, () => {
  nextTick(() => {
    setTimeout(() => {
      scrollbarRef.value?.setScrollTop(scrollbarRef.value.wrapRef!.scrollHeight);
    }, 100);
  });
});
</script>