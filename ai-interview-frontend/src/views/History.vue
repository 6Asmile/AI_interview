<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>我的面试历史</span>
        </div>
      </template>
      <el-table :data="historyList" v-loading="loading" style="width: 100%">
        <el-table-column prop="job_position" label="面试岗位" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="200">
           <template #default="scope">{{ new Date(scope.row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <!-- 【核心改造】根据状态动态显示按钮 -->
            <el-button 
              v-if="scope.row.status === 'finished'"
              size="small" 
              type="primary"
              @click="viewReport(scope.row.id)"
            >
              查看报告
            </el-button>
            <el-button 
              v-if="scope.row.status === 'running'"
              size="small" 
              type="warning"
              @click="resumeInterview(scope.row.id)"
            >
              继续面试
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getInterviewHistoryApi } from '@/api/modules/report';
import type { InterviewSessionItem } from '@/api/modules/interview';

const router = useRouter();
const loading = ref(true);
const historyList = ref<InterviewSessionItem[]>([]);

const fetchHistory = async () => {
  loading.value = true;
  try {
    historyList.value = await getInterviewHistoryApi();
  } catch (error) {
    console.error("获取面试历史失败", error);
  } finally {
    loading.value = false;
  }
};

onMounted(fetchHistory);

const viewReport = (sessionId: string) => {
  router.push({ name: 'ReportDetail', params: { id: sessionId } });
};

// 【新增】继续面试的函数
const resumeInterview = (sessionId: string) => {
  router.push({ name: 'InterviewRoom', params: { id: sessionId } });
};

const statusText = (status: string) => ({ pending: '待开始', running: '进行中', finished: '已完成', canceled: '已取消' }[status] || '未知');
const statusTagType = (status: string) => ({ pending: 'info', running: 'primary', finished: 'success', canceled: 'warning' }[status] || 'info');
</script>

<style scoped>
/* 样式无需改动 */
</style>