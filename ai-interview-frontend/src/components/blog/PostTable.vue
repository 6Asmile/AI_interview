<template>
  <el-table :data="posts" v-loading="isLoading" style="width: 100%">
    <el-table-column prop="title" label="标题" min-width="250" show-overflow-tooltip />

    <el-table-column v-if="showStatusColumn" label="状态" width="100">
      <template #default="scope">
        <el-tag :type="scope.row.status === 'published' ? 'success' : 'info'">
          {{ scope.row.status === 'published' ? '已发布' : '草稿' }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column prop="view_count" label="浏览量" width="100" />
    <el-table-column prop="like_count" label="点赞数" width="100" />
    <el-table-column label="最后更新" width="180">
      <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
    </el-table-column>

    <!-- 【核心修复】为操作列添加一个容器并设置样式 -->
    <el-table-column label="操作" width="240" fixed="right">
      <template #default="scope">
        <div class="action-buttons">
          <el-button size="small" @click="router.push({ name: 'PostEditor', params: { id: scope.row.id } })">编辑</el-button>
          <el-button v-if="scope.row.status === 'draft'" size="small" type="success" @click="publishDraft(scope.row.id)">发布</el-button>
          <el-button size="small" type="danger" @click="deletePost(scope.row.id)">删除</el-button>
          <el-button size="small" type="primary" plain @click="router.push({ name: 'PostDetail', params: { id: scope.row.id } })">查看</el-button>
        </div>
      </template>
    </el-table-column>

     <template #empty>
        <el-empty description="暂无文章" />
      </template>
  </el-table>
</template>

<script setup lang="ts">
import { defineProps, defineEmits } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElButton, ElTag, ElEmpty } from 'element-plus';
import { updatePostApi, deletePostApi } from '@/api/modules/blog';
import type { PostListItem } from '@/api/modules/blog';
import { formatDateTime } from '@/utils/format';

defineProps<{
  posts: PostListItem[];
  isLoading: boolean;
  showStatusColumn?: boolean;
}>();

const emit = defineEmits(['refresh']);

const router = useRouter();

const publishDraft = async (id: number) => {
  try {
    await updatePostApi(id, { status: 'published' });
    ElMessage.success('文章已发布！');
    emit('refresh');
  } catch (error) {
    ElMessage.error('发布失败');
  }
};

const deletePost = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定要删除这篇文章吗？', '警告', { type: 'warning' });
    await deletePostApi(id);
    ElMessage.success('删除成功');
    emit('refresh');
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败');
  }
};
</script>

<!-- 【核心修复】添加样式 -->
<style scoped>
.action-buttons {
  display: flex;
  gap: 8px; /* 使用 gap 添加间距 */
}
</style>