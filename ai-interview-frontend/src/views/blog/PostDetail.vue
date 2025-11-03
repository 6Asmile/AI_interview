<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { 
  ElMessage, ElSkeleton, ElRow, ElCol, ElCard, ElAvatar, 
  ElButton, ElTag, ElIcon 
} from 'element-plus';
import { Calendar, Timer, Pointer, Star, ChatDotRound } from '@element-plus/icons-vue';
import { getPostDetailApi, type PostDetail } from '@/api/modules/blog';
import { toggleLikeApi, toggleBookmarkApi, toggleFollowApi } from '@/api/modules/interactions';
import { formatDateTime } from '@/utils/format';
import { MdPreview, MdCatalog } from 'md-editor-v3';
import 'md-editor-v3/lib/preview.css';

const route = useRoute();
const postId = computed(() => Number(route.params.id));

const post = ref<PostDetail | null>(null);
const isLoading = ref(true);
const editorId = 'post-detail-preview';

// 响应式状态，用于控制按钮的激活状态
const isLiked = ref(false);
const isBookmarked = ref(false);
const isAuthorFollowed = ref(false);

const fetchData = async () => {
  if (!postId.value) return;
  isLoading.value = true;
  try {
    const postData = await getPostDetailApi(postId.value);
    post.value = postData;
    // 用 API 返回的数据初始化状态
    isLiked.value = postData.is_liked;
    isBookmarked.value = postData.is_bookmarked;
    isAuthorFollowed.value = postData.is_author_followed;
  } catch (error) {
    ElMessage.error('文章加载失败');
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchData);

// 处理交互的函数
const handleLike = async () => {
  if (!post.value) return;
  try {
    await toggleLikeApi(post.value.id);
    isLiked.value = !isLiked.value;
    // 乐观更新点赞数
    post.value.like_count += isLiked.value ? 1 : -1;
  } catch { ElMessage.error('操作失败，请先登录'); }
};

const handleBookmark = async () => {
  if (!post.value) return;
  try {
    await toggleBookmarkApi(post.value.id);
    isBookmarked.value = !isBookmarked.value;
    ElMessage.success(isBookmarked.value ? '收藏成功' : '已取消收藏');
  } catch { ElMessage.error('操作失败，请先登录'); }
};

const handleFollow = async () => {
  if (!post.value?.author) return;
  try {
    await toggleFollowApi(post.value.author.id);
    isAuthorFollowed.value = !isAuthorFollowed.value;
  } catch { ElMessage.error('操作失败，请先登录'); }
};
</script>

<template>
  <div class="post-detail-container">
    <el-row :gutter="30">
      <!-- 主内容区 -->
      <el-col :xs="24" :sm="24" :md="18">
        <el-card v-if="isLoading" shadow="never" class="main-card">
          <el-skeleton :rows="15" animated />
        </el-card>
        <el-card v-else-if="post" shadow="never" class="main-card">
          <template #header>
            <div class="post-header">
              <h1 class="post-title">{{ post.title }}</h1>
              <div class="author-meta">
                <el-avatar :size="40" :src="post.author.avatar || ''" />
                <div class="author-info">
                  <span class="author-name">{{ post.author.username }}</span>
                  <div class="meta-line">
                    <span><el-icon><Calendar /></el-icon> 发布于 {{ formatDateTime(post.published_at, 'YYYY-MM-DD') }}</span>
                    <span><el-icon><Timer /></el-icon> 阅读约 {{ post.read_time }} 分钟</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
          
          <div class="post-content">
            <MdPreview :editorId="editorId" :modelValue="post.content" />
          </div>

          <template #footer>
            <div class="post-footer">
              <div class="tags-line">
                <el-tag v-for="tag in post.tags" :key="tag.id" type="info" size="small" class="post-tag">
                  {{ tag.name }}
                </el-tag>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>

      <!-- 右侧边栏 -->
      <el-col :xs="24" :sm="24" :md="6">
        <div class="sticky-sidebar">
          <el-card v-if="post" shadow="never" class="sidebar-card">
             <div class="author-card">
                <el-avatar :size="50" :src="post.author.avatar || ''" />
                <span class="author-name-sidebar">{{ post.author.username }}</span>
                <el-button 
                  :type="isAuthorFollowed ? 'primary' : 'default'" 
                  :plain="!isAuthorFollowed"
                  size="small"
                  @click="handleFollow"
                >
                  {{ isAuthorFollowed ? '已关注' : '关注' }}
                </el-button>
             </div>
          </el-card>

          <el-card shadow="never" class="sidebar-card">
             <template #header>
              <strong>文章大纲</strong>
            </template>
            <div class="catalog-wrapper">
              <MdCatalog :editorId="editorId" :scrollElement="'.el-main'" />
            </div>
          </el-card>
        </div>
      </el-col>
    </el-row>

    <!-- 悬浮操作栏 -->
    <div class="action-bar" v-if="post">
      <div class="action-item" @click="handleLike">
        <el-button :type="isLiked ? 'primary' : 'default'" circle size="large">
          <el-icon size="24"><Pointer /></el-icon>
        </el-button>
        <span class="count">{{ post.like_count }}</span>
      </div>
      <div class="action-item">
        <el-button circle size="large">
          <el-icon size="24"><ChatDotRound /></el-icon>
        </el-button>
        <span class="count">{{ post.comment_count }}</span>
      </div>
      <div class="action-item" @click="handleBookmark">
        <el-button :type="isBookmarked ? 'warning' : 'default'" circle size="large">
          <el-icon size="24"><Star /></el-icon>
        </el-button>
        <span class="count">收藏</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.post-detail-container {
  padding: 20px 8%;
  background-color: #f4f5f5;
  position: relative; /* 为悬浮操作栏定位 */
}

.main-card {
  border-radius: 4px;
}

.post-header {
  padding-bottom: 20px;
  border-bottom: 1px solid #e5e6eb;
}

.post-title {
  font-size: 2.2rem;
  font-weight: 600;
  margin: 0 0 24px;
}

.author-meta {
  display: flex;
  align-items: center;
}

.author-info {
  margin-left: 12px;
}

.author-name {
  font-weight: 500;
  font-size: 1rem;
}

.meta-line {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
  font-size: 0.85rem;
  color: #909399;
}

.meta-line span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.post-content {
  padding: 20px 0;
}

:deep(.md-editor-preview) {
  font-size: 16px;
  line-height: 1.7;
}

.post-footer {
  padding-top: 20px;
}
.tags-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.post-tag {
  cursor: pointer;
}

.sticky-sidebar {
  position: sticky;
  top: 80px; /* 适配顶部导航栏高度 */
}
.sidebar-card {
  margin-bottom: 20px;
  border-radius: 4px;
}
.author-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.author-name-sidebar {
  font-weight: 600;
}
.catalog-wrapper {
  max-height: 60vh;
  overflow-y: auto;
}
/* 优化大纲样式 */
:deep(.md-editor-catalog-link span) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.action-bar {
  position: fixed;
  top: 200px;
  /* 动态计算位置，使其在主内容区左侧 */
  left: max(20px, calc((100vw - 1200px) / 2 - 80px)); 
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.action-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
}
.action-item .count {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}
</style>