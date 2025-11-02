<template>
  <div class="my-posts-container">
    <!-- 数据分析模块 -->
    <div class="stats-section">
      <el-row :gutter="20">
        <el-col :span="6">
          <StatsCard :icon="ViewIcon" :value="statsData.total_views" label="总阅读量" />
        </el-col>
        <el-col :span="6">
          <StatsCard :icon="PointerIcon" :value="statsData.total_likes" label="总点赞数" />
        </el-col>
        <el-col :span="6">
          <StatsCard :icon="ChatDotRoundIcon" :value="statsData.total_comments" label="总评论数" />
        </el-col>
        <el-col :span="6">
          <StatsCard :icon="StarIcon" :value="statsData.total_bookmarks" label="总收藏数" />
        </el-col>
      </el-row>
    </div>

    <!-- 文章列表模块 -->
    <el-card shadow="never" class="posts-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="全部文章" name="all"></el-tab-pane>
        <el-tab-pane label="已发布" name="published"></el-tab-pane>
        <el-tab-pane label="草稿箱" name="draft"></el-tab-pane>
      </el-tabs>
      <PostTable 
        :posts="postList" 
        :is-loading="isLoading" 
        :show-status-column="activeTab === 'all'"
        @refresh="fetchMyPosts" 
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { ElMessage, ElTabs, ElTabPane, ElCard, ElRow, ElCol } from 'element-plus';
import { View as ViewIcon, Pointer as PointerIcon, ChatDotRound as ChatDotRoundIcon, Star as StarIcon } from '@element-plus/icons-vue';
import { getMyPostsApi, getMyPostStatsApi } from '@/api/modules/blog';
import type { PostListItem } from '@/api/modules/blog';
import PostTable from '@/components/blog/PostTable.vue';
import StatsCard from '@/components/blog/StatsCard.vue';

const activeTab = ref('all'); // 默认显示全部文章
const postList = ref<PostListItem[]>([]);
const isLoading = ref(true);
const statsData = ref({
  total_views: 0,
  total_likes: 0,
  total_comments: 0,
  total_bookmarks: 0,
});

const fetchMyPosts = async () => {
  isLoading.value = true;
  try {
    const params: { status?: string } = {};
    if (activeTab.value !== 'all') {
      params.status = activeTab.value;
    }
    const response = await getMyPostsApi(params);
    postList.value = response.results;
  } catch (error) {
    ElMessage.error('加载文章列表失败');
  } finally {
    isLoading.value = false;
  }
};

const fetchStats = async () => {
  try {
    statsData.value = await getMyPostStatsApi();
  } catch (error) {
    ElMessage.error('加载统计数据失败');
  }
};

// 【核心修复】使用 watch 来响应 Tab 变化
watch(activeTab, () => {
  fetchMyPosts();
});

onMounted(() => {
  fetchMyPosts();
  fetchStats();
});
</script>

<style scoped>
.my-posts-container {
  padding: 24px;
}
.stats-section {
  margin-bottom: 20px;
}
.posts-card {
  border-radius: 8px;
}
</style>