<template>
  <div class="post-detail-container p-4 lg:p-8" v-loading="isLoading">
    <div v-if="post" class="max-w-4xl mx-auto bg-white rounded-lg shadow-lg overflow-hidden">
      <!-- 封面图 -->
      <img v-if="post.cover_image" :src="post.cover_image" class="w-full h-64 object-cover" alt="Post Cover" />
      
      <div class="p-6 md:p-10">
        <!-- 文章标题 -->
        <h1 class="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">{{ post.title }}</h1>
        
        <!-- 元数据 -->
        <div class="flex items-center gap-6 text-sm text-gray-500 mb-8 border-y py-3">
          <div class="flex items-center gap-2">
            <el-avatar :size="32" :src="post.author.avatar ?? undefined">{{ post.author.username.charAt(0).toUpperCase() }}</el-avatar>
            <span class="font-medium">{{ post.author.username }}</span>
          </div>
          <div class="flex items-center gap-2">
            <el-icon><Calendar /></el-icon>
            <span>发布于 {{ formatDate(post.published_at) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <el-icon><Timer /></el-icon>
            <span>阅读约 {{ post.read_time }} 分钟</span>
          </div>
        </div>
        
        <!-- 文章内容 -->
        <MarkdownRenderer :content="post.content" />

        <!-- 标签 -->
        <div v-if="post.tags && post.tags.length" class="mt-10 pt-6 border-t">
          <el-tag v-for="tag in post.tags" :key="tag.id" class="mr-2 mb-2">{{ tag.name }}</el-tag>
        </div>

        <!-- 评论区占位符 -->
        <div class="mt-12">
          <h3 class="text-2xl font-bold mb-6">评论区</h3>
          <!-- CommentSection.vue 组件将在这里 -->
          <div class="text-center text-gray-400 p-8 border rounded-lg">评论功能即将上线...</div>
        </div>
      </div>
    </div>
    <el-empty v-else-if="!isLoading" description="文章不存在或加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { getPostDetailApi, type PostDetail } from '@/api/modules/blog';
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue';
import { ElAvatar, ElIcon, ElTag, ElEmpty } from 'element-plus';
import { Calendar, Timer } from '@element-plus/icons-vue';
import dayjs from 'dayjs';

const route = useRoute();
const isLoading = ref(true);
const post = ref<PostDetail | null>(null);

const fetchPostDetail = async () => {
  isLoading.value = true;
  try {
    const postId = Number(route.params.id);
    post.value = await getPostDetailApi(postId);
  } catch (error) {
    console.error("Failed to fetch post detail:", error);
  } finally {
    isLoading.value = false;
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return '';
  return dayjs(dateString).format('YYYY年MM月DD日');
};

onMounted(() => {
  fetchPostDetail();
});
</script>

<style scoped>
/* 可以添加一些额外的样式来微调 */
.post-detail-container {
  background-color: #f3f4f6; /* 一个柔和的背景色 */
}
</style>