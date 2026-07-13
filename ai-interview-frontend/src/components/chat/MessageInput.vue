<!-- src/components/chat/MessageInput.vue (新建文件) -->
<template>
  <div class="message-composer">
    <!-- Toolbar -->
    <div class="composer-toolbar">
      <el-tooltip content="发送图片">
        <el-upload
          action="#"
          :show-file-list="false"
          :http-request="handleFileUpload"
          :before-upload="beforeImageUpload"
        >
          <div class="toolbar-action">
            <el-icon :size="18"><Picture /></el-icon>
          </div>
        </el-upload>
      </el-tooltip>
      <el-tooltip content="发送文件">
         <el-upload
          action="#"
          :show-file-list="false"
          :http-request="handleFileUpload"
          :before-upload="beforeFileUpload"
        >
          <div class="toolbar-action">
            <el-icon :size="18"><FolderOpened /></el-icon>
          </div>
        </el-upload>
      </el-tooltip>
    </div>

    <!-- Textarea -->
    <el-input
      class="composer-input"
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
    <div class="composer-footer">
      <span class="composer-count">{{ isUploading ? '上传中...' : `${newMessage.length} / 500` }}</span>
      <el-button class="composer-send" type="primary" @click="handleSend" :disabled="!newMessage.trim() && !isUploading">
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
import { uploadChatAttachmentApi } from '@/api/modules/chat';
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
    const response = await uploadChatAttachmentApi(options.file);
    
    const message_type = options.file.type.startsWith('image/') ? 'image' : 'file';

    chatStore.sendMessage({
      content: options.file.name, // 将文件名作为 content
      message_type: message_type,
      attachment_id: response.id,
    });

  } catch (error) {
    ElMessage.error('文件上传失败');
  } finally {
    isUploading.value = false;
  }
};
</script>

<style scoped>
.message-composer {
  padding: 18px 22px 20px;
  border-top: 1px solid #e8eef8;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
}

.composer-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.toolbar-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid #d8e3f5;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%);
  color: #5372a8;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toolbar-action:hover {
  border-color: #93b4f4;
  color: #2b62cd;
  box-shadow: 0 12px 20px rgba(65, 109, 192, 0.14);
  transform: translateY(-1px);
}

.composer-input :deep(.el-textarea__inner) {
  padding: 14px 16px;
  border: 1px solid #d8e2f2;
  border-radius: 18px;
  background: #fbfcff;
  box-shadow: inset 0 1px 2px rgba(85, 111, 157, 0.05);
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
}

.composer-count {
  color: #97a5bb;
  font-size: 13px;
}

.composer-send {
  min-width: 120px;
  min-height: 42px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 14px 24px rgba(42, 101, 216, 0.2);
}
</style>
