<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { 
  ElMessage, ElSkeleton, ElRow, ElCol, ElCard, ElAvatar, 
  ElButton, ElTag, ElIcon, ElDivider, ElEmpty
} from 'element-plus';
import { Calendar, Timer, Pointer, Star, ChatDotRound, EditPen } from '@element-plus/icons-vue';
import { getPostDetailApi, getPostCommentsApi, createCommentApi, type PostDetail, type CommentItem as Comment } from '@/api/modules/blog';
import { toggleLikeApi, toggleBookmarkApi, toggleFollowApi } from '@/api/modules/interactions';
import { formatDateTime } from '@/utils/format';
import { MdPreview, MdCatalog } from 'md-editor-v3';
import 'md-editor-v3/lib/preview.css';

// 导入新建的评论组件
import CommentBox from '@/components/blog/CommentBox.vue';
import CommentItem from '@/components/blog/CommentItem.vue';
import { useAuthStore } from '@/store/modules/auth';

const route = useRoute();
const authStore = useAuthStore();
const postId = computed(() => Number(route.params.id));

const post = ref<PostDetail | null>(null);
const comments = ref<Comment[]>([]);
const isLoading = ref(true);
const isLoadingComments = ref(true);
const isSubmittingComment = ref(false);
const editorId = 'post-detail-preview';

const isLiked = ref(false);
const isBookmarked = ref(false);
const isAuthorFollowed = ref(false);

const fetchData = async () => {
  if (!postId.value) return;
  isLoading.value = true;
  try {
    const postData = await getPostDetailApi(postId.value);
    post.value = postData;
    isLiked.value = postData.is_liked;
    isBookmarked.value = postData.is_bookmarked;
    isAuthorFollowed.value = postData.is_author_followed;
  } catch (error) {
    ElMessage.error('文章加载失败');
  } finally {
    isLoading.value = false;
  }
};

const fetchComments = async () => {
  isLoadingComments.value = true;
  try {
    // 【核心修正】由于全局分页开启，API 返回的是分页对象
    const response = await getPostCommentsApi(postId.value);
    comments.value = response.results;
  } catch (error) {
    ElMessage.error('评论加载失败');
  } finally {
    isLoadingComments.value = false;
  }
};

onMounted(() => {
  fetchData();
  fetchComments();
});

const handleLike = async () => {
  if (!authStore.isAuthenticated) {
    ElMessage.warning('请先登录');
    return;
  }
  if (!post.value) return;
  try {
    await toggleLikeApi(post.value.id);
    isLiked.value = !isLiked.value;
    post.value.like_count += isLiked.value ? 1 : -1;
  } catch { ElMessage.error('操作失败'); }
};

const handleBookmark = async () => {
  if (!authStore.isAuthenticated) {
    ElMessage.warning('请先登录');
    return;
  }
  if (!post.value) return;
  try {
    await toggleBookmarkApi(post.value.id);
    isBookmarked.value = !isBookmarked.value;
    ElMessage.success(isBookmarked.value ? '收藏成功' : '已取消收藏');
  } catch { ElMessage.error('操作失败'); }
};

const handleFollow = async () => {
  if (!authStore.isAuthenticated) {
    ElMessage.warning('请先登录');
    return;
  }
  if (!post.value?.author) return;
  try {
    await toggleFollowApi(post.value.author.id);
    isAuthorFollowed.value = !isAuthorFollowed.value;
  } catch { ElMessage.error('操作失败'); }
};



// 【核心修复】增强发表评论的逻辑
const handleCommentSubmit = async (content: string, clearContent: Function) => {
  isSubmittingComment.value = true;
  try {
    await createCommentApi(postId.value, { content });
    clearContent();
    ElMessage.success('评论发表成功');
    
    // 乐观更新评论数
    if (post.value) {
      post.value.comment_count += 1;
    }
    
    fetchComments(); // 重新加载评论列表
  } catch (error) {
    ElMessage.error('评论发表失败');
  } finally {
    isSubmittingComment.value = false;
  }
};

// 【核心新增】处理回复成功的逻辑
const handleReplySuccess = () => {
  if (post.value) {
    post.value.comment_count += 1;
  }
  fetchComments(); // 重新加载整个评论树
}

</script>

<template>
  <div class="post-detail-container">
    <el-row :gutter="30">
      <!-- 主内容区 -->
      <el-col :xs="24" :sm="24" :md="18">
        <el-card v-if="isLoading" shadow="never" class="main-card">
          <el-skeleton :rows="15" animated />
        </el-card>
        <template v-else-if="post">
          <el-card shadow="never" class="main-card">
            <template #header>
              <div class="post-header">
                <h1 class="post-title">{{ post.title }}</h1>
                <div class="author-meta">
                  <el-avatar :size="40" :src="post.author.avatar || ''" />
                  <div class="author-info">
                    <span class="author-name">{{ post.author.username }}</span>
                    <div class="meta-line">
                      <span v-if="post.published_at"><el-icon><Calendar /></el-icon> 发布于 {{ formatDateTime(post.published_at, 'YYYY-MM-DD') }}</span>
                      <span v-else><el-icon><EditPen /></el-icon> 更新于 {{ formatDateTime(post.updated_at, 'YYYY-MM-DD') }}</span>
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

          <!-- 评论区模块 -->
          <el-card shadow="never" class="main-card comment-section">
            <h3>{{ post.comment_count }} 条评论</h3>
            <CommentBox 
              v-if="authStore.isAuthenticated"
              placeholder="发表你的看法..."
              :is-submitting="isSubmittingComment"
              @submit="handleCommentSubmit"
            />
            <div v-else class="login-prompt">
              请<el-button text type="primary" @click="$router.push('/login')">登录</el-button>后发表评论
            </div>
            <el-divider />
            <div v-loading="isLoadingComments">
              <CommentItem
                v-for="comment in comments"
                :key="comment.id"
                :post-id="postId"
                :comment="comment"
                @reply-success="handleReplySuccess"
              />
              <el-empty v-if="!isLoadingComments && comments.length === 0" description="暂无评论，快来抢沙发吧！" />
            </div>
          </el-card>
        </template>
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
  position: relative;
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
  top: 80px;
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
:deep(.md-editor-catalog-link span) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.action-bar {
  position: fixed;
  top: 200px;
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

.comment-section {
  margin-top: 20px;
}
.comment-section h3 {
  margin-bottom: 20px;
}
.login-prompt {
  text-align: center;
  padding: 20px;
  color: #606266;
  background-color: #f9f9f9;
  border-radius: 4px;
}
</style>