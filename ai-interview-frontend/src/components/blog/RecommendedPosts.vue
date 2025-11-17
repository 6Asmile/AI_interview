<!-- src/components/blog/RecommendedPosts.vue (新建文件) -->
<template>
  <div v-if="isLoading || recommendedPosts.length > 0" class="mt-8">
    <h3 class="text-xl font-bold mb-4 text-gray-800">相关推荐</h3>
    <div v-if="isLoading" class="space-y-4">
      <!-- 可以放置骨架屏 -->
      <div v-for="i in 3" :key="i" class="h-20 bg-gray-200 rounded-lg animate-pulse"></div>
    </div>
    <div v-else class="space-y-4">
      <router-link
        v-for="post in recommendedPosts"
        :key="post.id"
        :to="{ name: 'PostDetail', params: { id: post.id } }"
        class="block p-4 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow duration-300"
      >
        <h4 class="font-semibold text-gray-900 truncate">{{ post.title }}</h4>
        <div class="text-sm text-gray-500 mt-1 flex items-center space-x-4">
          <span><i class="el-icon-view"></i> {{ post.view_count }}</span>
          <span><i class="el-icon-like"></i> {{ post.like_count }}</span>
        </div>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { getRecommendedPostsApi } from '@/api/modules/blog';
import type { PostListItem } from '@/api/modules/blog';
import { ElMessage } from 'element-plus';

const props = defineProps<{
  postId: number;
}>();

const recommendedPosts = ref<PostListItem[]>([]);
const isLoading = ref(false);

const fetchRecommendations = async (id: number) => {
  if (!id) return;
  isLoading.value = true;
  try {
    recommendedPosts.value = await getRecommendedPostsApi(id);
  } catch (error) {
    console.error('获取推荐文章失败:', error);
    ElMessage.error('加载相关推荐失败');
  } finally {
    isLoading.value = false;
  }
};

onMounted(() => {
  fetchRecommendations(props.postId);
});

// 监听 postId 变化，当用户在详情页之间跳转时重新加载
watch(() => props.postId, (newId) => {
  fetchRecommendations(newId);
});
</script>

<style scoped>
/* 使用 Element Plus 图标，需要确保已全局引入或按需引入 */
@import url("//unpkg.com/element-plus/dist/index.css");
.el-icon-view, .el-icon-like {
  margin-right: 4px;
}
</style>