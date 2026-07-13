<!-- src/components/chat/MessageItem.vue (完整代码) -->
<template>
  <div class="message-row" :class="isMe ? 'message-row--me' : 'message-row--peer'">
    <!-- 对方头像 -->
    <div v-if="!isMe" class="message-avatar-slot">
      <el-avatar :size="34" :src="message.sender.avatar || undefined" class="message-avatar">
        {{ message.sender.username.charAt(0).toUpperCase() }}
      </el-avatar>
    </div>
    
    <div class="message-content" :class="isMe ? 'message-content--me' : 'message-content--peer'">
      <!-- 对方用户名 -->
      <div v-if="!isMe" class="message-sender">{{ message.sender.username }}</div>
      
      <div
        class="message-bubble"
        :class="isMe ? 'message-bubble--me' : 'message-bubble--peer'"
      >
        <p v-if="message.revoked_at" class="revoked-message">消息已撤回</p>
        <!-- 1. 文本消息 -->
        <p v-else-if="message.message_type === 'text'" class="whitespace-pre-wrap">{{ message.content }}</p>
        
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
      <div class="message-time" :class="isMe ? 'message-time--me' : 'message-time--peer'">
        {{ formatDateTime(message.timestamp, 'HH:mm') }}
        <span v-if="message.edited_at"> · 已编辑</span>
        <span v-if="isMe"> · {{ deliveryText }}</span>
      </div>
    </div>
    
    <!-- 自己的头像 -->
    <div v-if="isMe" class="message-avatar-slot">
      <el-avatar :size="34" :src="authStore.avatar || undefined" class="message-avatar">
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
const deliveryText = computed(() => ({ pending: '发送中', sent: '已发送', delivered: '已送达', read: '已读', failed: '失败' }[props.message.delivery_status] || '已发送'));

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
.message-row {
  display: flex;
  margin-bottom: 18px;
}

.message-row--me {
  justify-content: flex-end;
}

.message-row--peer {
  justify-content: flex-start;
}

.message-avatar-slot {
  margin: 0 10px;
}

.message-avatar {
  box-shadow: 0 10px 18px rgba(72, 99, 145, 0.16);
}

.message-content {
  max-width: min(72%, 680px);
}

.message-content--me {
  align-items: flex-end;
}

.message-sender {
  margin-bottom: 6px;
  color: #7b8aa2;
  font-size: 12px;
}

.message-bubble {
  padding: 14px 16px;
  border-radius: 20px;
  line-height: 1.65;
  box-shadow: 0 14px 24px rgba(58, 87, 133, 0.08);
}

.message-bubble--me {
  background: linear-gradient(135deg, #2a65d8 0%, #5d9eff 100%);
  color: white;
  border-top-right-radius: 8px;
}

.message-bubble--peer {
  background: rgba(255, 255, 255, 0.92);
  color: #283752;
  border: 1px solid #dfE7f4;
  border-top-left-radius: 8px;
}

.message-time {
  margin-top: 6px;
  color: #9aa8bc;
  font-size: 12px;
}

.message-time--me {
  text-align: right;
}

/* 链接颜色适配背景 */
.message-bubble--me a {
  color: white;
}

.message-bubble--peer a {
  color: #1f2937;
}

/* 保留换行符 */
.whitespace-pre-wrap {
  white-space: pre-wrap;
  word-break: break-all;
}
.revoked-message { margin: 0; color: #98a2b3; font-style: italic; }

@media (max-width: 768px) {
  .message-content {
    max-width: 82%;
  }
}
</style>
