<!-- src/components/blog/PostTable.vue (新建文件) -->
<template>
  <el-table :data="posts" v-loading="isLoading" style="width: 100%">
    <el-table-column prop="title" label="标题" />
    <el-table-column prop="view_count" label="浏览量" width="100" />
    <el-table-column prop="like_count" label="点赞数" width="100" />
    <el-table-column label="最后更新" width="180">
      <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="220">
      <template #default="scope">
        <el-button size="small" @click="router.push({ name: 'PostEditor', params: { id: scope.row.id } })">编辑</el-button>
        <el-button v-if="scope.row.status === 'draft'" size="small" type="success" @click="publishDraft(scope.row.id)">发布</el-button>
        <el-button size="small" type="danger" @click="deletePost(scope.row.id)">删除</el-button>
        <el-button size="small" type="primary" @click="router.push({ name: 'PostDetail', params: { id: scope.row.id } })">查看</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { defineProps, defineEmits } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElButton } from 'element-plus';
import { updatePostApi, deletePostApi } from '@/api/modules/blog';
import type { PostListItem } from '@/api/modules/blog';
import { formatDateTime } from '@/utils/format';

defineProps<{
  posts: PostListItem[];
  isLoading: boolean;
}>();

const emit = defineEmits(['refresh']);

const router = useRouter();

const publishDraft = async (id: number) => {
  try {
    await updatePostApi(id, {
        status: 'published',
        content: ''
    });
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