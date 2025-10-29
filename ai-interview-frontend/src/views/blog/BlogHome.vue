<template>
  <div class="blog-home-container max-w-screen-xl mx-auto py-8 px-4">
    
    <div class="glass-card mb-6 p-3">
      <div class="flex items-center gap-2 text-sm font-medium text-gray-600">
        <el-button type="primary" link class="active-tab">全部</el-button>
        <el-button type="primary" link>最新</el-button>
        <el-button type="primary" link>热门</el-button>
      </div>
    </div>

    <div class="main-grid">
      <aside class="left-sidebar space-y-6">
        <div class="glass-card p-4">
          <h3 class="font-semibold mb-4 text-gray-700 border-l-4 border-blue-500 pl-3">文章分类</h3>
          <ul class="space-y-1 text-sm text-gray-600">
            <li v-for="cat in categoryList" :key="cat.id" class="category-item">
              {{ cat.name }}
            </li>
          </ul>
        </div>
      </aside>

      <main class="center-content space-y-5">
        <div 
          v-loading="isLoading"
          v-for="post in postList" 
          :key="post.id" 
          class="post-list-item-card glass-card flex gap-6 p-5"
          @click="goToDetail(post.id)"
        >
          <div class="flex-grow flex flex-col">
            <h2 class="text-xl font-bold text-gray-800 mb-2 line-clamp-1">
              {{ post.title }}
            </h2>
            <p class="text-sm text-gray-500 line-clamp-2 mb-4 flex-grow">
              {{ post.excerpt || '暂无摘要...' }}
            </p>
            <div class="flex items-center text-xs text-gray-400 gap-5 mt-auto">
              <div class="flex items-center gap-2 author-tag">
                <el-avatar :size="24" :src="post.author.avatar ?? undefined">{{ post.author.username.charAt(0).toUpperCase() }}</el-avatar>
                <span>{{ post.author.username }}</span>
              </div>
              <span>{{ formatDate(post.published_at) }}</span>
              <div class="flex items-center gap-4 ml-auto">
                <span class="flex items-center gap-1"><el-icon><View /></el-icon> {{ post.view_count }}</span>
                <span class="flex items-center gap-1"><el-icon><Pointer /></el-icon> {{ post.like_count }}</span>
                <span class="flex items-center gap-1"><el-icon><ChatDotSquare /></el-icon> {{ post.comment_count }}</span>
              </div>
            </div>
          </div>
          <div v-if="post.cover_image" class="flex-shrink-0 w-48 h-32 overflow-hidden rounded-md">
            <img :src="post.cover_image" class="w-full h-full object-cover transition-transform duration-500" alt="Cover"/>
          </div>
        </div>
        <el-empty v-if="!isLoading && postList.length === 0" description="暂无已发布的文章" />
      </main>

      <aside class="right-sidebar space-y-6">
        <div class="glass-card p-4">
          <h3 class="font-semibold mb-4 text-gray-700 border-l-4 border-blue-500 pl-3">创作者中心</h3>
          <el-button type="primary" class="w-full" size="large" @click="goToEditor()">
            <el-icon class="mr-2"><EditPen /></el-icon> 发布文章
          </el-button>
        </div>
        <div class="glass-card p-4">
          <h3 class="font-semibold mb-4 text-gray-700 border-l-4 border-blue-500 pl-3">热门文章</h3>
          <ul class="space-y-4 text-sm text-gray-600">
            <li v-for="(item, index) in hotList" :key="item.id" class="hot-post-item" @click="goToDetail(item.id)">
              <span :class="['rank', `rank-${index + 1}`]">{{ index + 1 }}</span>
              <span class="line-clamp-1">{{ item.title }}</span>
            </li>
          </ul>
        </div>
        <div class="glass-card p-4">
          <h3 class="font-semibold mb-4 text-gray-700 border-l-4 border-blue-500 pl-3">热门标签</h3>
          <div class="flex flex-wrap gap-2">
            <el-tag v-for="tag in tagList" :key="tag.id" effect="light" round class="cursor-pointer hover:opacity-80 transition-opacity">{{ tag.name }}</el-tag>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { getPostListApi, getTagListApi, getCategoryListApi, type PostListItem, type Tag, type Category } from '@/api/modules/blog';
import { ElCard, ElAvatar, ElIcon, ElEmpty, ElButton, ElTag } from 'element-plus';
import { View, ChatDotSquare, Pointer, EditPen } from '@element-plus/icons-vue';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const router = useRouter();
const isLoading = ref(true);
const postList = ref<PostListItem[]>([]);
const tagList = ref<Tag[]>([]);
const categoryList = ref<Category[]>([]);

const hotList = computed(() => [...postList.value].sort((a, b) => b.view_count - a.view_count).slice(0, 5));

const fetchInitialData = async () => {
  isLoading.value = true;
  try {
    const [postsRes, tagsRes, catsRes] = await Promise.all([
      getPostListApi(),
      getTagListApi(),
      getCategoryListApi(),
    ]);
    postList.value = postsRes;
    tagList.value = tagsRes;
    categoryList.value = catsRes;
  } catch (error) {
    console.error("Failed to fetch initial data:", error);
  } finally {
    isLoading.value = false;
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return '';
  return dayjs(dateString).fromNow();
};

const goToDetail = (id: number) => router.push({ name: 'PostDetail', params: { id } });
const goToEditor = () => router.push({ name: 'PostEditor' });

onMounted(() => {
  fetchInitialData();
});
</script>

<style scoped>
/* [核心修正] 整体布局与卡片样式 */
.main-grid { display: grid; grid-template-columns: 200px 1fr 280px; gap: 1.5rem; }
.glass-card { background: rgba(255, 255, 255, 0.65); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); }

/* 主内容区卡片样式 */
.post-list-item-card { cursor: pointer; display: flex; align-items: stretch; min-height: 11rem; }
.post-list-item-card:hover { transform: translateY(-5px) scale(1.02); box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12); }
.post-list-item-card:hover img { transform: scale(1.1); }

/* 左侧分类样式 */
.category-item { padding: 8px 12px; border-radius: 6px; cursor: pointer; transition: all 0.2s ease; }
.category-item:hover { background-color: rgba(60, 130, 255, 0.1); color: #3375b9; }

/* 右侧热门文章样式 */
.hot-post-item { display: flex; align-items: center; gap: 10px; padding: 4px 0; cursor: pointer; transition: color 0.2s ease; }
.hot-post-item:hover { color: #3375b9; }
.rank { font-style: italic; font-weight: bold; width: 20px; text-align: center; color: #9ca3af; }
.rank-1, .rank-2, .rank-3 { color: #ef4444; }

/* 响应式布局 */
@media (max-width: 1024px) {
  .main-grid { grid-template-columns: 1fr; }
  .left-sidebar, .right-sidebar { display: none; }
}
</style>