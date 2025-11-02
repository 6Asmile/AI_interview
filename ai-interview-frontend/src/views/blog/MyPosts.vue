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
      
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="chart-header">
            <span>近期数据趋势 (近7日)</span>
          </div>
        </template>
        <LineChart :options="chartOptions" />
      </el-card>
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
        @refresh="handleRefresh" 
      />
      
      <!-- 【核心修复】添加分页组件 -->
      <div class="pagination-container" v-if="pagination.total > pagination.pageSize">
        <el-pagination
          background
          layout="prev, pager, next, jumper, ->, total"
          :total="pagination.total"
          :page-size="pagination.pageSize"
          v-model:current-page="pagination.currentPage"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed, reactive } from 'vue';
import { ElMessage, ElTabs, ElTabPane, ElCard, ElRow, ElCol, ElPagination } from 'element-plus';
import { View as ViewIcon, Pointer as PointerIcon, ChatDotRound as ChatDotRoundIcon, Star as StarIcon } from '@element-plus/icons-vue';
import { getMyPostsApi, getMyPostStatsApi, getMyDailyStatsApi } from '@/api/modules/blog';
import type { PostListItem, DailyStatsData } from '@/api/modules/blog';
import PostTable from '@/components/blog/PostTable.vue';
import StatsCard from '@/components/blog/StatsCard.vue';
import LineChart from '@/components/common/LineChart.vue';
import type { EChartsOption } from 'echarts';

const activeTab = ref('all');
const postList = ref<PostListItem[]>([]);
const isLoading = ref(true);

// 【核心修复】将分页数据设为响应式对象
const pagination = reactive({
  currentPage: 1,
  pageSize: 10,
  total: 0,
});

const statsData = ref({
  total_views: 0,
  total_likes: 0,
  total_comments: 0,
  total_bookmarks: 0,
});

const dailyStats = ref<DailyStatsData>({
  labels: [],
  views: [],
  likes: [],
});

const chartOptions = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['浏览量', '点赞数'], top: 'bottom' },
  grid: { left: '3%', right: '4%', bottom: '10%', top: '10%', containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, data: dailyStats.value.labels },
  yAxis: { type: 'value' },
  series: [
    { name: '浏览量', type: 'line', data: dailyStats.value.views, smooth: true, areaStyle: {} },
    { name: '点赞数', type: 'line', data: dailyStats.value.likes, smooth: true, areaStyle: {} },
  ],
}));

const fetchMyPosts = async () => {
  isLoading.value = true;
  try {
    const params: { status?: string; page: number; page_size: number } = {
      page: pagination.currentPage,
      page_size: pagination.pageSize,
    };
    if (activeTab.value !== 'all') {
      params.status = activeTab.value;
    }
    const response = await getMyPostsApi(params);
    postList.value = response.results;
    pagination.total = response.count; // 更新总数
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

const fetchDailyStats = async () => {
  try {
    dailyStats.value = await getMyDailyStatsApi(7);
  } catch (error) {
    ElMessage.error('加载趋势数据失败');
  }
};

const handleRefresh = () => {
  fetchMyPosts();
  fetchStats();
  fetchDailyStats();
}

// 【核心修复】切换 Tab 时重置到第一页
watch(activeTab, () => {
  pagination.currentPage = 1;
  fetchMyPosts();
});

// 【核心修复】处理页码变化
const handlePageChange = (newPage: number) => {
  pagination.currentPage = newPage;
  fetchMyPosts();
};

onMounted(() => {
  handleRefresh();
});
</script>

<style scoped>
.my-posts-container {
  padding: 24px;
  background-color: #f5f7fa;
}
.stats-section {
  margin-bottom: 20px;
}
.chart-card {
  margin-top: 20px;
  border-radius: 8px;
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.posts-card {
  border-radius: 8px;
}
:deep(.el-tabs__header) {
  margin: 0 0 20px;
}
.pagination-container {
  display: flex;
  justify-content: flex-end; /* 右对齐 */
  margin-top: 24px;
}
</style>