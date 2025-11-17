<!-- src/components/chat/MessageInput.vue (新建文件) -->
<template>
  <div class="p-4 border-t bg-white">
    <!-- Toolbar -->
    <div class="flex items-center space-x-2 mb-2">
      <el-tooltip content="发送图片">
        <el-upload
          action="#"
          :show-file-list="false"
          :http-request="handleFileUpload"
          :before-upload="beforeImageUpload"
        >
          <el-icon class="cursor-pointer hover:text-blue-500" :size="20"><Picture /></el-icon>
        </el-upload>
      </el-tooltip>
      <el-tooltip content="发送文件">
         <el-upload
          action="#"
          :show-file-list="false"
          :http-request="handleFileUpload"
          :before-upload="beforeFileUpload"
        >
          <el-icon class="cursor-pointer hover:text-blue-500" :size="20"><FolderOpened /></el-icon>
        </el-upload>
      </el-tooltip>
    </div>

    <!-- Textarea -->
    <el-input
      ref="textareaRef"
      v-model="newMessage"
      type="textarea"
      :rows="4"
      placeholder="输入消息..."
      resize="none"
      @keydown.enter.prevent="handleSend"
      @input="handleTyping"
    />

    <!-- Footer -->
    <div class="flex justify-end items-center mt-2">
      <span class="text-sm text-gray-400 mr-4">{{ newMessage.length }} / 500</span>
      <el-button type="primary" @click="handleSend" :disabled="!newMessage.trim() && !isUploading">
        发送 (Enter)
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useChatStore } from '@/store/modules/chat';
import { ElMessage } from 'element-plus';
import { Picture, FolderOpened } from '@element-plus/icons-vue';
import { uploadFileApi } from '@/api/modules/common';
import type { UploadRequestOptions } from 'element-plus';
import { debounce } from 'lodash-es';

const chatStore = useChatStore();
const newMessage = ref('');
const isUploading = ref(false);

const handleSend = () => {
  if (!newMessage.value.trim()) return;
  chatStore.sendMessage({
    content: newMessage.value,
    message_type: 'text',
  });
  newMessage.value = '';
  // 发送后，立刻发送停止输入的状态
  sendStopTyping();
};

// --- "正在输入" 逻辑 ---
const sendStartTyping = debounce(() => {
    chatStore.sendTypingIndicator(true);
}, 300);

const sendStopTyping = debounce(() => {
    chatStore.sendTypingIndicator(false);
}, 2000); // 用户停止输入2秒后，发送停止状态

const handleTyping = () => {
    sendStartTyping();
    sendStopTyping();
};

// --- 文件上传逻辑 ---
const beforeImageUpload = (file: File) => {
  const isImage = file.type.startsWith('image/');
  if (!isImage) {
    ElMessage.error('只能上传图片文件!');
  }
  const isLt5M = file.size / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error('图片大小不能超过 5MB!');
  }
  return isImage && isLt5M;
};

const beforeFileUpload = (file: File) => {
  const isLt20M = file.size / 1024 / 1024 < 20;
  if (!isLt20M) {
    ElMessage.error('文件大小不能超过 20MB!');
  }
  return isLt20M;
}

const handleFileUpload = async (options: UploadRequestOptions) => {
  isUploading.value = true;
  try {
    const response = await uploadFileApi(options.file, 'chat_files');
    
    const message_type = options.file.type.startsWith('image/') ? 'image' : 'file';

    chatStore.sendMessage({
      content: options.file.name, // 将文件名作为 content
      message_type: message_type,
      file_url: response.file_url,
    });

  } catch (error) {
    ElMessage.error('文件上传失败');
  } finally {
    isUploading.value = false;
  }
};
</script>