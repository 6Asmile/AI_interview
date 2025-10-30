<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElTag, ElButton, ElTabs, ElTabPane, ElPagination } from 'element-plus';
import { getInterviewHistoryApi, getAnalysisHistoryApi } from '@/api/modules/report';
import { abandonUnfinishedInterviewApi, type InterviewSessionItem } from '@/api/modules/interview';
import type { ResumeAnalysisReportItem } from '@/api/modules/report';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const activeTab = ref('interviews');

// --- 面试记录的状态 ---
const interviewHistory = ref<InterviewSessionItem[]>([]);
const isLoadingInterviews = ref(true);
const interviewPagination = ref({
  currentPage: 1,
  pageSize: 10,
  total: 0,
});

// --- 简历评估记录的状态 ---
const analysisHistory = ref<ResumeAnalysisReportItem[]>([]);
const isLoadingAnalysis = ref(true);
const analysisPagination = ref({
  currentPage: 1,
  pageSize: 10,
  total: 0,
});

// --- 数据获取 ---
const fetchInterviewHistory = async () => {
  isLoadingInterviews.value = true;
  try {
    const params = { page: interviewPagination.value.currentPage, page_size: interviewPagination.value.pageSize };
    // 【核心修改】处理分页响应
    const response = await getInterviewHistoryApi(params);
    interviewHistory.value = response.results;
    interviewPagination.value.total = response.count;
  } catch (error) {
    ElMessage.error('面试记录加载失败');
  } finally {
    isLoadingInterviews.value = false;
  }
};

const fetchAnalysisHistory = async () => {
  isLoadingAnalysis.value = true;
  try {
    const params = { page: analysisPagination.value.currentPage, page_size: analysisPagination.value.pageSize };
    // 【核心修改】处理分页响应
    const response = await getAnalysisHistoryApi(params);
    analysisHistory.value = response.results;
    analysisPagination.value.total = response.count;
  } catch (error) {
    ElMessage.error('简历评估记录加载失败');
  } finally {
    isLoadingAnalysis.value = false;
  }
};

onMounted(() => {
  fetchInterviewHistory();
  fetchAnalysisHistory();
});

// --- 事件处理 ---
const handleInterviewPageChange = (page: number) => {
  interviewPagination.value.currentPage = page;
  fetchInterviewHistory();
};

const handleAnalysisPageChange = (page: number) => {
  analysisPagination.value.currentPage = page;
  fetchAnalysisHistory();
};

const handleAbandon = async (sessionId: string) => {
  try {
    await ElMessageBox.confirm('确定要放弃这次进行中的面试吗？', '确认', { type: 'warning' });
    await abandonUnfinishedInterviewApi();
    ElMessage.success('面试已放弃');
    fetchInterviewHistory(); // 刷新列表
  } catch (error) {
    if (error !== 'cancel') ElMessage.info('操作已取消');
  }
};

// --- 辅助函数 ---
const interviewStatusText = (status: string) => ({ running: '进行中', finished: '已完成', canceled: '已取消' }[status] || '未知');
const getResumeTitle = (resumeId: number | null) => (resumeId ? `简历ID: ${resumeId}` : '未关联简历');
</script>

<template>
  <div class="history-container">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="面试记录" name="interviews">
        <el-table :data="interviewHistory" v-loading="isLoadingInterviews">
          <el-table-column prop="job_position" label="面试岗位" />
          <el-table-column label="状态">
            <template #default="scope">
              <el-tag>{{ interviewStatusText(scope.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="开始时间">
            <template #default="scope">{{ formatDateTime(scope.row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="操作">
            <template #default="scope">
              <el-button v-if="scope.row.status === 'finished'" size="small" @click="router.push({ name: 'ReportDetail', params: { id: scope.row.id } })">查看报告</el-button>
              <el-button v-if="scope.row.status === 'running'" size="small" type="primary" @click="router.push({ name: 'InterviewRoom', params: { id: scope.row.id } })">继续面试</el-button>
              <el-button v-if="scope.row.status === 'running'" size="small" type="danger" @click="handleAbandon(scope.row.id)">放弃面试</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-container" v-if="interviewPagination.total > interviewPagination.pageSize">
          <el-pagination background layout="prev, pager, next" :total="interviewPagination.total" :page-size="interviewPagination.pageSize" v-model:current-page="interviewPagination.currentPage" @current-change="handleInterviewPageChange" />
        </div>
      </el-tab-pane>
      
      <el-tab-pane label="简历评估记录" name="analysis">
        <el-table :data="analysisHistory" v-loading="isLoadingAnalysis">
          <el-table-column label="关联简历">
            <template #default="scope">{{ getResumeTitle(scope.row.resume) }}</template>
          </el-table-column>
          <el-table-column prop="overall_score" label="匹配度得分" />
          <el-table-column label="评估时间">
             <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作">
            <template #default="scope">
              <el-button size="small" @click="router.push({ name: 'AnalysisReportDetail', params: { reportId: scope.row.id } })">查看详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-container" v-if="analysisPagination.total > analysisPagination.pageSize">
          <el-pagination background layout="prev, pager, next" :total="analysisPagination.total" :page-size="analysisPagination.pageSize" v-model:current-page="analysisPagination.currentPage" @current-change="handleAnalysisPageChange" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.history-container {
  padding: 24px;
}
.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>