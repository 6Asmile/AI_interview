<!-- src/components/blog/CommentBox.vue (终极完整版) -->
<template>
  <div class="comment-box">
    <el-avatar :size="40" :src="authStore.avatar || ''" />
    <div class="editor-area">
      <MdEditor
        v-model="content"
        :placeholder="placeholder"
        :toolbars="toolbars"
        @onUploadImg="handleUploadImage"
        :preview="false"
        language="zh-CN"
        class="comment-editor"
      >
        <template #defToolbars>
          <Emoji @onInsert="insertContent" />
        </template>
      </MdEditor>
      <div class="actions">
        <el-button type="primary" @click="handleSubmit" :loading="isSubmitting">发表评论</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import { ElMessage, ElButton, ElAvatar } from 'element-plus';
import { MdEditor, type ToolbarNames } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { Emoji } from '@vavt/v3-extension';
import '@vavt/v3-extension/lib/asset/style.css';
import { uploadFileApi } from '@/api/modules/common'; // 导入通用上传API

const props = defineProps<{
  placeholder?: string;
  isSubmitting: boolean;
}>();

const emit = defineEmits(['submit']);

const authStore = useAuthStore();
const content = ref('');

const toolbars: ToolbarNames[] = ['bold', 'italic', 'strikeThrough', 'quote', 'link', 'codeRow', 'image'];

const insertContent = (val: string) => {
  content.value += val;
};

const handleSubmit = () => {
  if (!content.value.trim()) {
    ElMessage.warning('评论内容不能为空');
    return;
  }
  emit('submit', content.value, () => {
    content.value = '';
  });
};

const handleUploadImage = async (files: File[], callback: (urls: string[]) => void) => {
  const backendBaseUrl = import.meta.env.VITE_API_BASE_URL.replace('/api/v1', '');
  const urls = await Promise.all(
    files.map(async (file) => {
      try {
        const res = await uploadFileApi(file, 'comment_images');
        return `${backendBaseUrl}${res.file_url}`;
      } catch (e) {
        ElMessage.error('图片上传失败');
        return '';
      }
    })
  );
  callback(urls.filter(url => url));
};
</script>

<style scoped>
.comment-box { display: flex; gap: 15px; }
.editor-area { flex-grow: 1; }
.actions { margin-top: 10px; text-align: right; }
.comment-editor { height: 150px; }
</style>