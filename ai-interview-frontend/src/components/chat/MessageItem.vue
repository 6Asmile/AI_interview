<!-- src/components/chat/MessageItem.vue (完整代码) -->
<template>
  <div class="mb-4 flex" :class="isMe ? 'justify-end' : 'justify-start'">
    <!-- 对方头像 -->
    <div v-if="!isMe" class="mr-3">
      <el-avatar :size="32" :src="message.sender.avatar || undefined">
        {{ message.sender.username.charAt(0).toUpperCase() }}
      </el-avatar>
    </div>
    
    <div class="max-w-xs lg:max-w-md">
      <!-- 对方用户名 -->
      <div v-if="!isMe" class="text-xs text-gray-500 mb-1">{{ message.sender.username }}</div>
      
      <div
        class="p-3 rounded-lg"
        :class="isMe ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-800'"
      >
        <!-- 1. 文本消息 -->
        <p v-if="message.message_type === 'text'" class="whitespace-pre-wrap">{{ message.content }}</p>
        
        <!-- 2. 图片消息 -->
        <div v-else-if="message.message_type === 'image'">
          <el-image
            :src="getFullUrl(message.file_url)"
            :preview-src-list="[getFullUrl(message.file_url)]"
            fit="cover"
            class="max-w-full h-auto rounded-md cursor-zoom-in"
            style="max-height: 200px;"
          >
            <template #error>
              <div class="flex justify-center items-center bg-gray-100 w-24 h-24 rounded text-gray-400">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
        </div>

        <!-- 3. 文件消息 -->
        <div v-else-if="message.message_type === 'file'" class="flex items-center">
          <el-icon class="mr-2" :size="24"><Folder /></el-icon>
          <a 
            :href="getFullUrl(message.file_url)" 
            target="_blank" 
            rel="noopener noreferrer" 
            class="hover:underline break-all"
          >
            {{ message.content || '点击下载文件' }}
          </a>
        </div>
        
        <!-- 4. 其他类型 (语音/视频) -->
        <div v-else class="flex items-center">
           <el-icon class="mr-2"><Warning /></el-icon>
           <span>不支持的消息类型: {{ message.message_type }}</span>
        </div>
      </div>
      
      <!-- 时间戳 -->
      <div class="text-xs text-gray-400 mt-1" :class="isMe ? 'text-right' : 'text-left'">
        {{ formatDateTime(message.timestamp, 'HH:mm') }}
      </div>
    </div>
    
    <!-- 自己的头像 -->
    <div v-if="isMe" class="ml-3">
      <el-avatar :size="32" :src="authStore.avatar || undefined">
        {{ authStore.username?.charAt(0).toUpperCase() }}
      </el-avatar>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import type { Message } from '@/api/modules/chat';
import { formatDateTime } from '@/utils/format';
import { Folder, Warning, Picture } from '@element-plus/icons-vue';

const props = defineProps<{
  message: Message;
}>();

const authStore = useAuthStore();
const isMe = computed(() => props.message.sender.id === authStore.user?.id);

// 【核心新增】获取完整的资源 URL
const getFullUrl = (url: string | null) => {
  if (!url) return '';
  // 如果已经是完整路径（如 http开头 或 blob预览流），直接返回
  if (url.startsWith('http') || url.startsWith('https') || url.startsWith('blob:')) {
    return url;
  }

  // 拼接后端地址
  // 在开发环境，直接指向 Django 端口，确保图片能加载
  // 在生产环境，通常基础路径为空（走 Nginx 代理）或者指向 CDN
  let baseUrl = '';
  
  if (import.meta.env.DEV) {
    baseUrl = 'http://127.0.0.1:8000';
  } else {
    // 生产环境尝试从 VITE_API_BASE_URL 推断，或者留空使用相对路径
    baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/api\/v1\/?$/, '') || '';
  }

  // 处理斜杠拼接，防止出现 //media
  if (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);
  if (!url.startsWith('/')) url = `/${url}`;

  return `${baseUrl}${url}`;
};
</script>

<style scoped>
/* 链接颜色适配背景 */
.bg-blue-500 a {
  color: white;
}
.bg-gray-200 a {
  color: #1f2937;
}
/* 保留换行符 */
.whitespace-pre-wrap {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>