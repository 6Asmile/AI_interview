<template>
  <div class="message-composer">
    <div class="composer-toolbar">
      <el-tooltip content="发送图片">
        <el-upload action="#" :show-file-list="false" :http-request="handleFileUpload" :before-upload="beforeImageUpload">
          <button class="toolbar-action" type="button" aria-label="发送图片">
            <el-icon :size="18"><Picture /></el-icon>
          </button>
        </el-upload>
      </el-tooltip>
      <el-tooltip content="发送文件">
        <el-upload action="#" :show-file-list="false" :http-request="handleFileUpload" :before-upload="beforeFileUpload">
          <button class="toolbar-action" type="button" aria-label="发送文件">
            <el-icon :size="18"><FolderOpened /></el-icon>
          </button>
        </el-upload>
      </el-tooltip>
      <el-popover placement="top-start" :width="288" trigger="click">
        <template #reference>
          <button class="toolbar-action emoji-trigger" type="button" aria-label="选择表情">☺</button>
        </template>
        <div class="emoji-panel">
          <div v-if="recentEmojis.length" class="emoji-section">
            <span class="emoji-label">最近使用</span>
            <div class="emoji-grid">
              <button v-for="emoji in recentEmojis" :key="`recent-${emoji}`" type="button" @click="insertEmoji(emoji)">{{ emoji }}</button>
            </div>
          </div>
          <span class="emoji-label">常用表情</span>
          <div class="emoji-grid">
            <button v-for="emoji in emojis" :key="emoji" type="button" @click="insertEmoji(emoji)">{{ emoji }}</button>
          </div>
        </div>
      </el-popover>
    </div>

    <el-input
      v-model="newMessage"
      class="composer-input"
      type="textarea"
      :rows="4"
      :maxlength="5000"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      resize="none"
      @keydown="handleKeydown"
      @paste="handlePaste"
      @compositionstart="isComposing = true"
      @compositionend="isComposing = false"
      @input="handleTyping"
    />

    <div class="composer-footer">
      <span class="composer-count">{{ isUploading ? '上传中...' : `${newMessage.length} / 5000` }}</span>
      <el-button class="composer-send" type="primary" :loading="isUploading" :disabled="!newMessage.trim() || isUploading" @click="handleSend">
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import type { UploadRequestOptions } from 'element-plus';
import { FolderOpened, Picture } from '@element-plus/icons-vue';
import { debounce } from 'lodash-es';
import { uploadChatAttachmentApi } from '@/api/modules/chat';
import { useChatStore } from '@/store/modules/chat';

const chatStore = useChatStore();
const newMessage = ref('');
const isUploading = ref(false);
const isComposing = ref(false);
const emojis = ['😀', '😄', '😂', '😊', '🙂', '😉', '😍', '🤔', '😅', '😭', '😮', '😴', '👍', '👏', '🙏', '💪', '🎉', '❤️', '🔥', '✅', '💡', '🚀', '👀', '🙌'];
const recentEmojis = ref<string[]>(loadRecentEmojis());

function loadRecentEmojis(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem('ifaceoff_recent_emojis') || '[]');
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, 8) : [];
  } catch {
    return [];
  }
}

function insertEmoji(emoji: string) {
  newMessage.value += emoji;
  recentEmojis.value = [emoji, ...recentEmojis.value.filter(item => item !== emoji)].slice(0, 8);
  localStorage.setItem('ifaceoff_recent_emojis', JSON.stringify(recentEmojis.value));
  handleTyping();
}

function handleSend() {
  const content = newMessage.value.trim();
  if (!content || isUploading.value) return;
  chatStore.sendMessage({ content, message_type: 'text' });
  newMessage.value = '';
  sendStopTyping.flush();
  chatStore.sendTypingIndicator(false);
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
  if (isComposing.value || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  handleSend();
}

const sendStartTyping = debounce(() => chatStore.sendTypingIndicator(true), 300);
const sendStopTyping = debounce(() => chatStore.sendTypingIndicator(false), 2000);

function handleTyping() {
  sendStartTyping();
  sendStopTyping();
}

function beforeImageUpload(file: File) {
  const validType = file.type.startsWith('image/');
  const validSize = file.size < 5 * 1024 * 1024;
  if (!validType) ElMessage.error('只能上传图片文件');
  if (!validSize) ElMessage.error('图片大小不能超过 5MB');
  return validType && validSize;
}

function beforeFileUpload(file: File) {
  const validSize = file.size < 20 * 1024 * 1024;
  if (!validSize) ElMessage.error('文件大小不能超过 20MB');
  return validSize;
}

async function uploadAndSend(file: File) {
  const isImage = file.type.startsWith('image/');
  if (!(isImage ? beforeImageUpload(file) : beforeFileUpload(file))) return;
  isUploading.value = true;
  try {
    const response = await uploadChatAttachmentApi(file);
    chatStore.sendMessage({
      content: file.name || (isImage ? '剪贴板图片' : '附件'),
      message_type: isImage ? 'image' : 'file',
      attachment_id: response.id,
    });
  } catch {
    ElMessage.error('文件上传失败');
  } finally {
    isUploading.value = false;
  }
}

async function handleFileUpload(options: UploadRequestOptions) {
  await uploadAndSend(options.file);
}

async function handlePaste(event: ClipboardEvent) {
  const imageItem = Array.from(event.clipboardData?.items || []).find(item => item.kind === 'file' && item.type.startsWith('image/'));
  if (!imageItem) return;
  const pastedFile = imageItem.getAsFile();
  if (!pastedFile) return;
  event.preventDefault();
  const extension = pastedFile.type.split('/')[1] || 'png';
  const file = new File([pastedFile], `clipboard-${Date.now()}.${extension}`, { type: pastedFile.type });
  await uploadAndSend(file);
}
</script>

<style scoped>
.message-composer { padding: 18px 22px 20px; border-top: 1px solid #e8eef8; background: rgba(255, 255, 255, 0.96); }
.composer-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.toolbar-action { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border: 1px solid #d8e3f5; border-radius: 6px; background: #fff; color: #5372a8; cursor: pointer; }
.toolbar-action:hover { border-color: #7aa7ef; color: #2b62cd; background: #f5f8ff; }
.emoji-trigger { font-size: 20px; }
.emoji-section { margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #edf1f7; }
.emoji-label { display: block; margin-bottom: 8px; color: #7b879b; font-size: 12px; }
.emoji-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px; }
.emoji-grid button { width: 30px; height: 30px; padding: 0; border: 0; border-radius: 4px; background: transparent; font-size: 19px; cursor: pointer; }
.emoji-grid button:hover { background: #eef4ff; }
.composer-input :deep(.el-textarea__inner) { padding: 12px 14px; border: 1px solid #d8e2f2; border-radius: 6px; background: #fbfcff; box-shadow: none; }
.composer-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; }
.composer-count { color: #97a5bb; font-size: 13px; }
.composer-send { min-width: 96px; min-height: 38px; border-radius: 6px; }
</style>
