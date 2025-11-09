<!-- src/components/blog/CommentBox.vue (重构版) -->
<template>
  <div class="comment-box">
    <el-avatar :size="40" :src="authStore.avatar || ''" />
    <div class="editor-area">
      <MdEditor
        v-model="content"
        :placeholder="placeholder"
        :toolbars="toolbars"
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

defineProps<{
  placeholder?: string;
  isSubmitting: boolean;
}>();

const emit = defineEmits(['submit']);

const authStore = useAuthStore();
const content = ref('');

const toolbars: ToolbarNames[] = ['bold', 'italic', 'strikeThrough', 'quote', 'link', 'codeRow'];

const insertContent = (emoji: string) => {
  content.value = `${content.value}${emoji}`;
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
</script>

<style scoped>
.comment-box { display: flex; gap: 15px; }
.editor-area { flex-grow: 1; }
.actions { margin-top: 10px; text-align: right; }
.comment-editor { height: 120px; }
</style>