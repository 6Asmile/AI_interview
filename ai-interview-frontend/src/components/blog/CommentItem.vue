<template>
  <div class="comment-item">
    <el-avatar :size="40" :src="comment.author.avatar || ''" class="author-avatar" />
    <div class="comment-body">
      <div class="comment-header">
        <span class="author-name">{{ comment.author.username }}</span>
      </div>
      <div class="comment-content">
        <!-- 【核心修复】使用 MdPreview 渲染内容 -->
        <MdPreview :modelValue="comment.content" :editorId="`comment-${comment.id}`" />
      </div>
      <div class="comment-footer">
        <span class="comment-time">{{ formatDateTime(comment.created_at, 'YYYY-MM-DD HH:mm') }}</span>
        <el-button text type="primary" size="small" @click="isReplyBoxVisible = !isReplyBoxVisible">
          {{ isReplyBoxVisible ? '取消回复' : '回复' }}
        </el-button>
      </div>
      
      <el-collapse-transition>
        <div v-if="isReplyBoxVisible" class="reply-box">
          <CommentBox 
            :placeholder="`回复 @${comment.author.username}`"
            :is-submitting="isSubmittingReply"
            @submit="handleReplySubmit" 
          />
        </div>
      </el-collapse-transition>

      <div v-if="comment.replies && comment.replies.length > 0" class="replies-container">
        <div class="toggle-replies" @click="isRepliesVisible = !isRepliesVisible">
          {{ isRepliesVisible ? '收起回复' : `展开 ${comment.replies.length} 条回复` }}
          <el-icon class="toggle-icon"><ArrowUp v-if="isRepliesVisible" /><ArrowDown v-else /></el-icon>
        </div>
        <el-collapse-transition>
          <div v-show="isRepliesVisible" class="replies-list">
            <CommentItem 
              v-for="reply in comment.replies" 
              :key="reply.id"
              :post-id="postId" 
              :comment="reply"
              @reply-success="emit('reply-success')"
            />
          </div>
        </el-collapse-transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits } from 'vue';
import { ElAvatar, ElButton, ElMessage, ElCollapseTransition, ElIcon } from 'element-plus';
import { ArrowUp, ArrowDown } from '@element-plus/icons-vue';
// 【核心新增】导入 MdPreview
import { MdPreview } from 'md-editor-v3';
import 'md-editor-v3/lib/preview.css';

import type { CommentItem as Comment } from '@/api/modules/blog';
import { createCommentApi } from '@/api/modules/blog';
import { formatDateTime } from '@/utils/format';
import CommentBox from './CommentBox.vue';

// 递归组件需要显式声明名称
defineOptions({
  name: 'CommentItem'
});

const props = defineProps<{
  postId: number;
  comment: Comment;
}>();

const emit = defineEmits(['reply-success']);

const isReplyBoxVisible = ref(false);
const isSubmittingReply = ref(false);
const isRepliesVisible = ref(true); // 默认展开第一层回复

const handleReplySubmit = async (content: string, clearContent: Function) => {
  isSubmittingReply.value = true;
  try {
    await createCommentApi(props.postId, {
      content: content,
      parent: props.comment.id,
    });
    isReplyBoxVisible.value = false;
    clearContent();
    ElMessage.success('回复成功');
    if (!isRepliesVisible.value) {
      isRepliesVisible.value = true;
    }
    emit('reply-success');
  } catch (error) {
    ElMessage.error('回复失败');
  } finally {
    isSubmittingReply.value = false;
  }
};
</script>

<style scoped>
.comment-item { 
  display: flex; 
  gap: 15px; 
  margin-top: 20px; 
}
.comment-body { 
  flex-grow: 1; 
}
.author-avatar {
  flex-shrink: 0;
}
.comment-header {
  display: flex;
  align-items: center;
}
.author-name { 
  font-weight: 500; 
  color: #333;
}
.comment-content {
  margin: 8px 0;
}
/* 【核心新增】为 MdPreview 去掉多余的边距和背景 */
.comment-content :deep(.md-editor-preview) {
  padding: 0;
  background-color: transparent;
}
.comment-content :deep(.md-editor-preview-wrapper) {
  padding: 0;
}
.comment-footer { 
  display: flex; 
  align-items: center; 
  gap: 10px; 
  color: #909399; 
  font-size: 13px; 
}
.reply-box { 
  margin-top: 15px; 
}
.replies-container {
  margin-top: 15px;
}
.toggle-replies {
  color: var(--el-color-primary);
  cursor: pointer;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 10px;
}
.toggle-icon {
  transition: transform 0.2s;
}
.replies-list { 
  border-left: 2px solid #e5e6eb; 
  padding-left: 20px; 
}
</style>