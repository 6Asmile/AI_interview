<template>
  <div class="blog-home-container p-4 lg:p-8 max-w-screen-2xl mx-auto">
    <div class="mb-8 text-center">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">探索求职与技术的智慧</h1>
      <p class="text-gray-500">精选文章、深度见解与实战经验</p>
    </div>
    <el-button @click="router.push({ name: 'PostEditor' })">写文章</el-button>
    <div v-loading="isLoading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <el-card 
        v-for="post in postList" 
        :key="post.id" 
        class="post-card cursor-pointer hover:shadow-xl transition-all duration-300 border-0"
        :body-style="{ padding: '0px' }"
        shadow="hover"
        @click="router.push({ name: 'PostDetail', params: { id: post.id } })"
      >
        <div class="relative aspect-video overflow-hidden bg-gray-100">
          <img 
            v-if="post.cover_image" 
            :src="post.cover_image" 
            class="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
            alt="Cover Image"
          />
          <div v-else class="w-full h-full flex items-center justify-center text-gray-300">
            <el-icon :size="48"><Picture /></el-icon>
          </div>
          <div v-if="post.category" class="absolute top-4 left-4 bg-blue-600 text-white text-xs px-3 py-1 rounded-full font-medium shadow-sm">
            {{ post.category.name }}
          </div>
        </div>

        <div class="p-5 flex flex-col gap-3">
          <h2 class="text-xl font-bold text-gray-800 line-clamp-2 hover:text-blue-600 transition-colors">
            {{ post.title }}
          </h2>
          <p class="text-gray-500 text-sm line-clamp-3 flex-grow">
            {{ post.excerpt || '暂无摘要...' }}
          </p>

          <div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 text-xs text-gray-400">
            <div class="flex items-center gap-2">
              <el-avatar :size="24" :src="post.author.avatar ?? undefined">
                {{ post.author.username.charAt(0).toUpperCase() }}
              </el-avatar>
              <span>{{ post.author.username }}</span>
            </div>
            <div class="flex items-center gap-4">
              <span class="flex items-center gap-1"><el-icon><View /></el-icon> {{ post.view_count }}</span>
              <span class="flex items-center gap-1"><el-icon><ChatDotSquare /></el-icon> {{ post.comment_count }}</span>
              <span>{{ formatDate(post.published_at) }}</span>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-empty v-if="!isLoading && postList.length === 0" description="暂无文章" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
// [核心修正] API 函数返回类型已在 API 文件中更新，这里无需修改
import { getPostListApi, type PostListItem } from '@/api/modules/blog';
import { ElCard, ElAvatar, ElIcon, ElEmpty } from 'element-plus';
import { Picture, View, ChatDotSquare } from '@element-plus/icons-vue';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const router = useRouter();
const isLoading = ref(true);
const postList = ref<PostListItem[]>([]);

const fetchPosts = async () => {
  isLoading.value = true;
  try {
    // [核心修正] 直接将返回的数组赋值给 postList
    const res = await getPostListApi();
    postList.value = res;
  } catch (error) {
    console.error("Failed to fetch posts:", error);
  } finally {
    isLoading.value = false;
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return '';
  return dayjs(dateString).fromNow();
};

onMounted(() => {
  fetchPosts();
});
</script>

<style scoped>
.post-card:hover {
  transform: translateY(-4px);
}
</style>