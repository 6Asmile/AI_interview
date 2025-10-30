<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElSkeleton, ElSkeletonItem, ElButton, ElTag, ElRow, ElCol, ElIcon } from 'element-plus';
import { EditPen, CollectionTag, View as ViewIcon, Pointer, ChatDotRound } from '@element-plus/icons-vue';
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

// --- 核心新增: 中间内容区的排序 Tab ---
const activeContentTab = ref<'latest' | 'recommended'>('latest');
const activeCategorySlug = ref<string | null>(null);

const router = useRouter();
const authStore = useAuthStore();

// --- API 调用与数据处理 ---
const fetchPosts = async () => {
  isLoading.value = true;
  try {
    const params: any = {};
    
    // 根据分类筛选
    if (activeCategorySlug.value) {
      params.category__slug = activeCategorySlug.value;
    }

    // 根据 Tab 决定排序方式
    if (activeContentTab.value === 'latest') {
      params.ordering = '-published_at';
    } else { // 'recommended'
      params.ordering = '-view_count'; // 暂时用浏览量最高作为推荐
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
const handleCategoryClick = (slug: string | null) => {
  activeCategorySlug.value = slug;
  fetchPosts(); // 重新获取文章
};

const handleContentTabClick = (tab: 'latest' | 'recommended') => {
  activeContentTab.value = tab;
  fetchPosts(); // 重新获取文章
};

// --- 生命周期钩子 ---
onMounted(() => {
  fetchPosts();
  fetchSidebarData();
});
</script>

<template>
  <div class="blog-home-container">
    <el-row :gutter="20">
      <!-- 左侧边栏 -->
      <el-col :xs="24" :sm="4" :md="4">
        <div class="sticky-sidebar left-sidebar">
          <div class="sidebar-module">
            <ul class="category-nav-list">
              <li :class="{ active: activeCategorySlug === null }" @click="handleCategoryClick(null)">
                <el-icon><CollectionTag /></el-icon> 综合
              </li>
              <li
                v-for="cat in categories"
                :key="cat.id"
                :class="{ active: activeCategorySlug === cat.slug }"
                @click="handleCategoryClick(cat.slug)">
                <!-- 可以在这里加入图标 -->
                {{ cat.name }}
              </li>
            </ul>
          </div>
        </div>
      </el-col>

      <!-- 中间主内容区 -->
      <el-col :xs="24" :sm="14" :md="14">
        <div class="main-content">
          <div class="content-header">
            <div class="content-tabs">
              <span :class="{ active: activeContentTab === 'recommended' }" @click="handleContentTabClick('recommended')">推荐</span>
              <span :class="{ active: activeContentTab === 'latest' }" @click="handleContentTabClick('latest')">最新</span>
            </div>
             <router-link :to="{ name: 'PostEditor' }" v-if="authStore.isAuthenticated">
              <el-button type="primary" :icon="EditPen">写文章</el-button>
            </router-link>
          </div>
          
          <div class="posts-list">
            <div v-if="isLoading">
              <!-- Skeleton Loader -->
            </div>
            <template v-else>
              <router-link v-for="post in posts" :key="post.id" :to="{ name: 'PostDetail', params: { id: post.id } }" class="post-card-link">
                <div class="post-card">
                  <div class="card-body">
                    <h3 class="card-title">{{ post.title }}</h3>
                    <p class="card-excerpt">{{ post.excerpt }}</p>
                    <div class="card-meta">
                      <span class="meta-author">{{ post.author.username || "佚名" }}</span>
                      <div class="meta-stats">
                        <span class="stat-item"><el-icon><ViewIcon /></el-icon>{{ post.view_count }}</span>
                        <span class="stat-item"><el-icon><Pointer /></el-icon>{{ post.like_count }}</span>
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
        </div>
      </el-col>

      <!-- 右侧边栏 -->
      <el-col :xs="24" :sm="6" :md="6">
        <div class="sticky-sidebar right-sidebar">
          <div class="sidebar-module">
            <h4 class="module-title">热门文章</h4>
            <ul class="hot-posts-list">
              <li v-for="(hot, index) in hotPosts" :key="hot.id">
                <span class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
                <router-link :to="{ name: 'PostDetail', params: { id: hot.id } }" class="hot-post-link">{{ hot.title }}</router-link>
              </li>
            </ul>
          </div>
           <div class="sidebar-module">
            <h4 class="module-title">标签云</h4>
            <div class="tag-cloud">
               <el-tag v-for="tag in tags" :key="tag.id" class="tag-item" effect="plain" round>
                  {{ tag.name }}
                </el-tag>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.blog-home-container {
  padding: 20px 5%; /* 使用百分比边距，适应更宽的屏幕 */
  background-color: #f4f5f5;
}

/* 核心：粘性侧边栏 */
.sticky-sidebar {
  position: sticky;
  top: 20px; /* 距离顶部的距离 */
}

/* 左侧边栏 */
.left-sidebar .sidebar-module {
  background: #fff;
  padding: 8px;
  border-radius: 4px;
}
.category-nav-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.category-nav-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s, color 0.2s;
  font-size: 1rem;
}
.category-nav-list li:hover {
  background-color: #f0f2f5;
}
.category-nav-list li.active {
  background-color: #eaf2ff;
  color: #1e80ff;
  font-weight: 600;
}

/* 中间主内容区 */
.main-content {
  background-color: #fff;
  border-radius: 4px;
}
.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e6eb;
}
.content-tabs {
  display: flex;
  gap: 20px;
  font-size: 1rem;
}
.content-tabs span {
  cursor: pointer;
  color: #8a919f;
}
.content-tabs span.active {
  color: #1e80ff;
  font-weight: 600;
}

/* 文章列表卡片 */
.post-card-link { text-decoration: none; color: inherit; }
.post-card {
  display: flex;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid #e5e6eb;
}
.post-card:last-child { border-bottom: none; }
.card-body {
  flex: 1;
  padding-right: 20px;
  min-width: 0;
}
.card-title {
  margin: 0 0 8px;
  font-size: 1.15rem;
  font-weight: 600;
  color: #252933;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-excerpt {
  margin: 0 0 12px;
  color: #8a919f;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  display: flex;
  align-items: center;
  color: #8a919f;
  font-size: 0.85rem;
}
.meta-author {
  margin-right: 12px;
}
.meta-stats {
  display: flex;
  align-items: center;
  gap: 12px;
}
.stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.card-cover {
  flex-shrink: 0;
  width: 120px;
  height: 80px;
  border-radius: 4px;
  overflow: hidden;
}
.cover-image { width: 100%; height: 100%; object-fit: cover; }
.no-posts { text-align: center; padding: 60px; color: #909399; }

/* 右侧边栏 */
.right-sidebar .sidebar-module {
  background: #fff;
  padding: 20px;
  border-radius: 4px;
  margin-bottom: 20px;
}
.module-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e6eb;
}
.hot-posts-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.hot-posts-list li {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.rank-badge {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  color: #909399;
  font-weight: 600;
  margin-right: 12px;
}
.rank-badge.rank-1, .rank-badge.rank-2, .rank-badge.rank-3 {
  color: #fff;
  background-color: #ff9a2e;
}
.rank-badge.rank-2 { background-color: #ffb837; }
.rank-badge.rank-3 { background-color: #ffd141; }

.hot-post-link {
  text-decoration: none;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hot-post-link:hover { color: #1e80ff; }

.tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
.tag-item { cursor: pointer; }
</style>