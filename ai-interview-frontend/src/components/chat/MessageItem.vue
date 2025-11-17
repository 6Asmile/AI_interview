<!-- src/components/chat/MessageItem.vue (新建文件) -->
<template>
  <div class="mb-4 flex" :class="isMe ? 'justify-end' : 'justify-start'">
    <div v-if="!isMe" class="mr-3">
      <el-avatar :size="32" :src="message.sender.avatar || undefined">
        {{ message.sender.username.charAt(0) }}
      </el-avatar>
    </div>
    <div class="max-w-xs lg:max-w-md">
      <div v-if="!isMe" class="text-xs text-gray-500 mb-1">{{ message.sender.username }}</div>
      <div
        class="p-3 rounded-lg"
        :class="isMe ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-800'"
      >
        <!-- 文本消息 -->
        <p v-if="message.message_type === 'text'" class="whitespace-pre-wrap">{{ message.content }}</p>
        
        <!-- 图片消息 -->
        <div v-else-if="message.message_type === 'image'">
          <el-image
            :src="message.file_url!"
            :preview-src-list="[message.file_url!]"
            fit="cover"
            class="max-w-full h-auto rounded-md"
            style="max-height: 200px;"
          />
        </div>

        <!-- 文件消息 -->
        <div v-else-if="message.message_type === 'file'" class="flex items-center">
          <el-icon class="mr-2" :size="24"><Folder /></el-icon>
          <a :href="message.file_url!" target="_blank" rel="noopener noreferrer" class="hover:underline">
            {{ message.content || '点击下载文件' }}
          </a>
        </div>
        
        <!-- 其他类型 (语音/视频) 暂作占位 -->
        <div v-else class="flex items-center">
           <el-icon class="mr-2"><Warning /></el-icon>
           <span>不支持的消息类型: {{ message.message_type }}</span>
        </div>
      </div>
       <div class="text-xs text-gray-400 mt-1" :class="isMe ? 'text-right' : 'text-left'">
        {{ formatDateTime(message.timestamp, 'HH:mm') }}
      </div>
    </div>
    <div v-if="isMe" class="ml-3">
      <el-avatar :size="32" :src="authStore.avatar || undefined">
        {{ authStore.username?.charAt(0) }}
      </el-avatar>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import type { Message } from '@/api/modules/chat';
import { formatDateTime } from '@/utils/format';
import { Folder, Warning } from '@element-plus/icons-vue';

const props = defineProps<{
  message: Message;
}>();

const authStore = useAuthStore();
const isMe = computed(() => props.message.sender.id === authStore.user?.id);
</script>

<style scoped>
/* 确保 a 标签颜色在不同背景下都可见 */
.bg-blue-500 a {
  color: white;
}
.bg-gray-200 a {
  color: #1f2937; /* text-gray-800 */
}
.whitespace-pre-wrap {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>