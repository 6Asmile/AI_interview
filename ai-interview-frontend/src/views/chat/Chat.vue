<!-- src/views/chat/Chat.vue (修改后) -->
<template>
  <div class="chat-page">
    <div class="chat-page-header">
      <div>
        <p class="chat-page-kicker">Private Messaging</p>
        <h1>我的私信</h1>
        <p>在这里，你可以与朋友们畅所欲言，分享心情，讨论话题，建立更紧密的联系。</p>
      </div>
    </div>
    <el-container class="chat-workbench">
      <el-aside width="320px" class="chat-sidebar">
        <ConversationList />
      </el-aside>
      <el-main class="chat-main">
        <ChatWindow />
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router'; // <-- 导入 useRoute
import ConversationList from '@/components/chat/ConversationList.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
import { useChatStore } from '@/store/modules/chat';

const chatStore = useChatStore();
const route = useRoute(); // <-- 获取当前路由信息

onMounted(() => {
  // 【核心新增】检查 URL 中是否带有 userId 参数
  const userId = route.params.userId;
  if (userId && typeof userId === 'string') {
    // 如果有，则立即调用 action 发起对话
    chatStore.startAndSelectConversation(parseInt(userId, 10));
  }
});

onUnmounted(() => {
  chatStore.disconnect();
});
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: calc(100vh - 60px);
  padding: 22px;
  background:
    radial-gradient(circle at top left, rgba(71, 132, 255, 0.12), transparent 30%),
    linear-gradient(180deg, #f7faff 0%, #f2f5fb 100%);
}

.chat-page-header {
  padding: 24px 28px;
  border: 1px solid rgba(201, 214, 236, 0.7);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 40px rgba(47, 74, 119, 0.08);
  backdrop-filter: blur(14px);
}

.chat-page-kicker {
  margin: 0 0 8px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.chat-page-header h1 {
  margin: 0 0 8px;
  color: #1c2d4f;
  font-size: 28px;
}

.chat-page-header p:last-child {
  margin: 0;
  color: #62728f;
}

.chat-workbench {
  flex: 1;
  min-height: 0;
  border: 1px solid rgba(201, 214, 236, 0.75);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 24px 55px rgba(43, 67, 108, 0.1);
  overflow: hidden;
}

.chat-sidebar {
  border-right: 1px solid #e6edf8;
  background: linear-gradient(180deg, #f9fbff 0%, #f3f7ff 100%);
}

.chat-main {
  padding: 0;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
}

@media (max-width: 900px) {
  .chat-page {
    padding: 16px;
  }

  .chat-page-header {
    padding: 20px;
  }
}
</style>
