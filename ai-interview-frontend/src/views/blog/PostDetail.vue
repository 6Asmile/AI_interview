<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { 
  ElMessage, ElSkeleton, ElRow, ElCol, ElCard, ElAvatar, 
  ElButton, ElTag, ElIcon 
} from 'element-plus';
import { Calendar, Timer } from '@element-plus/icons-vue';
import { getPostDetailApi, type PostDetail } from '@/api/modules/blog';
import { formatDateTime } from '@/utils/format';

// 【核心修正】从 md-editor-v3 导入预览和目录组件
import { MdPreview, MdCatalog } from 'md-editor-v3';
import 'md-editor-v3/lib/preview.css';

const route = useRoute();
const postId = computed(() => Number(route.params.id));

const post = ref<PostDetail | null>(null);
const isLoading = ref(true);
const editorId = 'post-detail-preview'; // 给预览组件一个唯一的ID

const fetchData = async () => {
  if (!postId.value) return;
  isLoading.value = true;
  try {
    post.value = await getPostDetailApi(postId.value);
  } catch (error) {
    ElMessage.error('文章加载失败');
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchData);
</script>

<template>
  <div class="post-detail-container">
    <el-row :gutter="20">
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
            <!-- 【核心修正】使用 MdPreview 组件渲染文章内容 -->
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
                <el-button type="primary" plain size="small">关注</el-button>
             </div>
          </el-card>

          <el-card shadow="never" class="sidebar-card">
             <template #header>
              <strong>文章大纲</strong>
            </template>
            <div class="catalog-wrapper">
              <!-- 【核心修正】使用 MdCatalog 组件，并通过 editorId 与预览组件关联 -->
              <MdCatalog :editorId="editorId" :scrollElement="'.el-main'" />
            </div>
          </el-card>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
/* 样式与上一版完全相同，无需修改 */
.post-detail-container{padding:20px 8%;background-color:#f4f5f5}.main-card{border-radius:4px}.post-header{padding-bottom:20px;border-bottom:1px solid #e5e6eb}.post-title{font-size:2.2rem;font-weight:600;margin:0 0 24px}.author-meta{display:flex;align-items:center}.author-info{margin-left:12px}.author-name{font-weight:500;font-size:1rem}.meta-line{display:flex;align-items:center;gap:16px;margin-top:4px;font-size:.85rem;color:#909399}.meta-line span{display:inline-flex;align-items:center;gap:4px}.post-content{padding:20px 0}:deep(.md-editor-preview){font-size:16px;line-height:1.7}.post-footer{padding-top:20px}.tags-line{display:flex;flex-wrap:wrap;gap:8px}.post-tag{cursor:pointer}.sticky-sidebar{position:sticky;top:20px}.sidebar-card{margin-bottom:20px;border-radius:4px}.author-card{display:flex;flex-direction:column;align-items:center;gap:10px}.author-name-sidebar{font-weight:600}.catalog-wrapper{max-height:60vh;overflow-y:auto}
</style>