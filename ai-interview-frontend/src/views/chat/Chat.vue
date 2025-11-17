<!-- src/views/chat/Chat.vue (修改后) -->
<template>
  <div class="page-container h-full flex">
    <el-container class="h-full bg-white rounded-lg shadow-md">
      <el-aside width="300px" class="border-r">
        <ConversationList />
      </el-aside>
      <el-main class="p-0">
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
.page-container {
  padding: 20px;
  height: calc(100vh - 60px);
}
</style>