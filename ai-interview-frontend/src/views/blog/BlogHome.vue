<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage, ElSkeleton, ElSkeletonItem, ElButton, ElTag, ElRow, ElCol, ElIcon } from 'element-plus';
import { EditPen, View as ViewIcon, Pointer, ChatDotRound } from '@element-plus/icons-vue';
import { getPostListApi, getCategoryListApi, getTagListApi } from '@/api/modules/blog';
import type { PostListItem, Category, Tag } from '@/api/modules/blog';
import { formatDateTime } from '@/utils/format';
import { useAuthStore } from '@/store/modules/auth';

// --- 响应式状态定义 ---
const posts = ref<PostListItem[]>([]);
const categories = ref<Category[]>([]);
const tags = ref<Tag[]>([]);
const hotPosts = ref<PostListItem[]>([]);
const isLoading = ref(true);

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore(); // 获取认证状态

const activeSlug = ref<{ type: 'category' | 'tag' | null, value: string | null }>({
  type: route.query.type as any || null,
  value: route.query.slug as string || null
});


// --- 数据获取逻辑 ---
const fetchPosts = async () => {
  isLoading.value = true;
  try {
    const params: any = { ordering: '-published_at' };
    if (activeSlug.value.type === 'category' && activeSlug.value.value) {
      params.category__slug = activeSlug.value.value;
    } else if (activeSlug.value.type === 'tag' && activeSlug.value.value) {
      params.tags__slug = activeSlug.value.value;
    }
    posts.value = await getPostListApi(params);
  } catch (error) {
    ElMessage.error('文章列表加载失败');
    console.error(error);
  } finally {
    isLoading.value = false;
  }
};

const fetchSidebarData = async () => {
  try {
    [categories.value, tags.value, hotPosts.value] = await Promise.all([
      getCategoryListApi(),
      getTagListApi(),
      getPostListApi({ ordering: '-view_count', limit: 5 })
    ]);
  } catch (error) {
    ElMessage.error('侧边栏信息加载失败');
    console.error(error);
  }
};

// --- 交互处理 ---
const handleFilterClick = (type: 'category' | 'tag' | null, slug: string | null) => {
  activeSlug.value = { type, value: slug };
  router.push({ query: slug ? { type, slug } : {} });
};


// --- 生命周期与侦听器 ---
onMounted(() => {
  fetchPosts();
  fetchSidebarData();
});

watch(
  () => route.query,
  (newQuery) => {
    activeSlug.value = {
        type: (newQuery.type as 'category' | 'tag' | null) || null,
        value: (newQuery.slug as string | null) || null,
    };
    fetchPosts();
  }
);
</script>

<template>
  <div class="blog-home-container">
    <!-- 核心修复: 将页面标题栏移出 el-row，使其成为独立的、横跨整个页面的部分 -->
    <div class="page-header">
      <h2 class="page-title">社区文章</h2>
      <router-link :to="{ name: 'PostEditor' }" v-if="authStore.isAuthenticated">
        <el-button type="primary" :icon="EditPen">写文章</el-button>
      </router-link>
    </div>

    <el-row :gutter="20">
      <!-- 主内容区域：文章列表 -->
      <el-col :xs="24" :sm="18">
        <div class="posts-list">
          <div v-if="isLoading">
            <el-skeleton v-for="n in 5" :key="n" style="margin-bottom: 1px;" animated>
               <template #template>
                  <div style="display: flex; align-items: center; padding: 20px; background: #fff; border-bottom: 1px solid #f0f2f5;">
                    <div style="flex: 1;">
                      <el-skeleton-item variant="p" style="width: 50%; margin-bottom: 10px;" />
                      <el-skeleton-item variant="text" style="width: 80%;" />
                      <el-skeleton-item variant="text" style="width: 30%; margin-top: 10px;" />
                    </div>
                    <el-skeleton-item variant="image" style="width: 150px; height: 100px; margin-left: 20px;" />
                  </div>
                </template>
            </el-skeleton>
          </div>
          <template v-else>
            <router-link v-for="post in posts" :key="post.id" :to="{ name: 'PostDetail', params: { id: post.id } }" class="post-card-link">
               <div class="post-card">
                 <div class="card-body">
                   <h3 class="card-title">{{ post.title }}</h3>
                   <p class="card-excerpt">{{ post.excerpt }}</p>
                   <!-- 核心修复: 添加点赞、评论、浏览量显示 -->
                   <div class="card-meta">
                      <span class="meta-author">{{ post.author.username || "佚名" }}</span>
                      <span class="meta-date">{{ formatDateTime(post.published_at, 'yyyy-MM-dd') }}</span>
                      <div class="meta-stats">
                        <span class="stat-item"><el-icon><ViewIcon /></el-icon>{{ post.view_count }}</span>
                        <span class="stat-item"><el-icon><Pointer /></el-icon>{{ post.like_count }}</span>
                        <span class="stat-item"><el-icon><ChatDotRound /></el-icon>{{ post.comment_count }}</span>
                      </div>
                   </div>
                 </div>
                 <div v-if="post.cover_image" class="card-cover">
                   <img :src="post.cover_image" alt="文章封面" class="cover-image">
                 </div>
               </div>
            </router-link>
            <div v-if="!posts.length && !isLoading" class="no-posts">
              <p>暂无文章</p>
            </div>
          </template>
        </div>
      </el-col>

      <!-- 侧边栏 -->
      <el-col :xs="24" :sm="6">
        <div class="sidebar">
          <div class="sidebar-module">
            <h4 class="module-title">分类</h4>
            <ul class="category-list">
              <li
                :class="{ active: activeSlug.type === null }"
                @click="handleFilterClick(null, null)">
                全部
              </li>
              <li
                v-for="cat in categories"
                :key="cat.id"
                :class="{ active: activeSlug.type === 'category' && activeSlug.value === cat.slug }"
                @click="handleFilterClick('category', cat.slug)">
                {{ cat.name }}
              </li>
            </ul>
          </div>
          
          <div class="sidebar-module">
            <h4 class="module-title">标签</h4>
            <div class="tag-cloud">
               <el-tag
                  v-for="tag in tags"
                  :key="tag.id"
                  class="tag-item"
                  :effect="activeSlug.type === 'tag' && activeSlug.value === tag.slug ? 'dark' : 'plain'"
                  @click="handleFilterClick('tag', tag.slug)">
                  {{ tag.name }}
                </el-tag>
            </div>
          </div>

          <div class="sidebar-module">
            <h4 class="module-title">热门推荐</h4>
            <ul class="hot-posts-list">
              <li v-for="hot in hotPosts" :key="hot.id">
                <router-link :to="{ name: 'PostDetail', params: { id: hot.id } }" class="hot-post-link">{{ hot.title }}</router-link>
              </li>
            </ul>
          </div>
          <div class="sidebar-module">
            <h4 class="module-title">友情链接</h4>
            <ul class="friend-links">
              <li><a href="https://csdn.net" target="_blank">CSDN</a></li>
              <li><a href="https://juejin.cn" target="_blank">掘金</a></li>
            </ul>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.blog-home-container {
  padding: 20px;
  background-color: #f5f7fa; /* 浅灰色背景，提升质感 */
}

/* 页面头部样式 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 1.75rem;
  color: #303133;
  margin: 0;
}

/* 文章列表容器 */
.posts-list {
  background-color: #fff;
  border-radius: 4px;
  overflow: hidden; /* 保证内部的边框不会溢出 */
  border: 1px solid #e4e7ed;
}

.post-card-link {
  text-decoration: none;
  color: inherit;
  display: block;
}

.post-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start; /* 顶部对齐 */
  padding: 24px;
  border-bottom: 1px solid #f0f2f5;
  transition: background-color 0.3s ease;
}

.post-card:last-child {
  border-bottom: none;
}

.post-card:hover {
  background-color: #fafcff;
}

.card-body {
  flex: 1;
  padding-right: 24px;
  min-width: 0;
}

.card-cover {
  flex-shrink: 0;
  width: 180px;
  height: 120px;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 4px;
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}


.card-title {
  margin: 0 0 8px;
  font-size: 1.25rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #303133;
}

.card-excerpt {
  margin: 0 0 16px; /* 增加与meta的间距 */
  color: #606266;
  font-size: 0.9rem;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  text-overflow: ellipsis;
  min-height: 2.8rem; 
}

/* Meta 数据样式 */
.card-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap; /* 允许换行 */
  gap: 16px; /* 统一间距 */
  font-size: 0.85rem;
  color: #909399;
}
.meta-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto; /* 核心：将统计数据推到最右侧 */
}
.stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.stat-item .el-icon {
  font-size: 1.1em;
}

.no-posts {
  text-align: center;
  padding: 60px;
  color: #909399;
  font-size: 1rem;
}

/* 侧边栏样式 */
.sidebar {
  padding: 24px;
  background-color: #fff;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}

.sidebar-module {
  margin-bottom: 30px;
}
.sidebar-module:last-child {
  margin-bottom: 0;
}

.module-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f2f5;
}

.category-list, .hot-posts-list, .friend-links {
  list-style: none;
  padding: 0;
  margin: 0;
}

.category-list li {
  padding: 10px 4px;
  cursor: pointer;
  border-radius: 4px;
  transition: color 0.2s, background-color 0.2s;
  font-size: 0.95rem;
  color: #606266;
}

.category-list li:hover {
  background-color: #f5f7fa;
  color: #409eff;
}

.category-list li.active {
  color: #409eff;
  font-weight: 600;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  cursor: pointer;
}

.hot-post-link, .friend-links a {
  text-decoration: none;
  color: #606266;
  font-size: 0.9rem;
  display: block;
  padding: 6px 0;
  transition: color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hot-post-link:hover, .friend-links a:hover {
  color: #409eff;
}
</style>