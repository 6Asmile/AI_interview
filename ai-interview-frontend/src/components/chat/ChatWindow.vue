<!-- src/components/chat/ChatWindow.vue -->
<template>
  <div v-if="activeConversation" class="chat-window-shell">
    <!-- Header -->
    <div class="chat-window-header">
      <div class="chat-peer-meta">
        <el-avatar :src="getOtherParticipant(activeConversation)?.avatar || undefined" :size="44" class="chat-peer-avatar">
          {{ (getOtherParticipant(activeConversation)?.username || '?').charAt(0).toUpperCase() }}
        </el-avatar>
        <div>
          <span class="chat-peer-name">
            {{ getOtherParticipant(activeConversation)?.username || '对话中...' }}
          </span>
          <p class="chat-peer-status">{{ chatStore.otherUserTypingStatus ? '正在输入...' : '在线私信中' }}</p>
        </div>
      </div>
    </div>

    <!-- Message Area -->
    <el-scrollbar ref="scrollbarRef" class="chat-message-scroll">
      <MessageItem
        v-for="message in chatStore.activeMessages"
        :key="message.id"
        :message="message"
      />
       <div v-if="chatStore.otherUserTypingStatus" class="chat-typing-row">
        <div class="chat-typing-pill">
          对方正在输入...
        </div>
      </div>
    </el-scrollbar>

    <!-- Input Area -->
    <MessageInput />
  </div>
  <div v-else class="chat-window-empty">
    <div class="empty-card">
      <p class="empty-kicker">Direct Message</p>
      <h3>选择一个对话开始聊天</h3>
      <p>左侧列表会保留你最近的会话记录，点击即可继续沟通。</p>
    </div>
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

<style scoped>
.chat-window-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-window-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid #e9eef7;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
}

.chat-peer-meta {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chat-peer-avatar {
  box-shadow: 0 12px 24px rgba(79, 108, 155, 0.18);
}

.chat-peer-name {
  display: block;
  color: #1d2f4e;
  font-size: 18px;
  font-weight: 700;
}

.chat-peer-status {
  margin: 4px 0 0;
  color: #7a89a2;
  font-size: 13px;
}

.chat-message-scroll {
  flex: 1;
  padding: 22px;
  background:
    radial-gradient(circle at top left, rgba(89, 140, 255, 0.07), transparent 28%),
    linear-gradient(180deg, #fbfcff 0%, #f5f8fe 100%);
}

.chat-typing-row {
  display: flex;
  justify-content: flex-start;
  margin-top: 8px;
}

.chat-typing-pill {
  padding: 10px 14px;
  border: 1px solid #d9e3f3;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #6e7f99;
  font-size: 13px;
  box-shadow: 0 10px 20px rgba(72, 100, 146, 0.08);
}

.chat-window-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  background: linear-gradient(180deg, #fcfdff 0%, #f7faff 100%);
}

.empty-card {
  width: min(420px, 100%);
  padding: 34px 28px;
  border: 1px solid #dfe8f8;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 22px 38px rgba(50, 75, 118, 0.08);
  text-align: center;
}

.empty-kicker {
  margin: 0 0 8px;
  color: #6781b0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.empty-card h3 {
  margin: 0 0 10px;
  color: #203252;
  font-size: 24px;
}

.empty-card p:last-child {
  margin: 0;
  color: #72819a;
  line-height: 1.7;
}
</style>
