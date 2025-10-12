<!-- src/views/History.vue -->
<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>我的面试历史</span>
        </div>
      </template>
      <el-table :data="historyList" v-loading="isLoading" style="width: 100%">
        <el-table-column prop="job_position" label="面试岗位" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="200">
          <!-- started_at 可能为空，增加保护 -->
          <template #default="scope">{{ scope.row.started_at ? new Date(scope.row.started_at).toLocaleString() : 'N/A' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button v-if="scope.row.status === 'finished'" link type="primary" @click="viewReport(scope.row.id)">查看报告</el-button>
            
            <template v-if="scope.row.status === 'running'">
              <el-button link type="success" @click="continueInterview(scope.row.id)">继续面试</el-button>
              <el-popconfirm
                title="确定要放弃这场面试吗？此操作不可恢复。"
                @confirm="handleAbandon"
              >
                <template #reference>
                  <el-button link type="danger">放弃面试</el-button>
                </template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
// 【核心修复#1】从正确的模块导入 API
import { getInterviewHistoryApi } from '@/api/modules/report'; 
import { abandonUnfinishedInterviewApi, type InterviewSessionItem } from '@/api/modules/interview';
import { ElMessage, ElPopconfirm } from 'element-plus';

const router = useRouter();
const historyList = ref<InterviewSessionItem[]>([]);
const isLoading = ref(true);

const fetchHistory = async () => {
  isLoading.value = true;
  try {
    historyList.value = await getInterviewHistoryApi();
  } catch (error) {
    ElMessage.error('加载面试历史失败');
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchHistory);

const viewReport = (id: string) => {
  router.push({ name: 'ReportDetail', params: { id } });
};

const continueInterview = (id:string) => {
  router.push({ name: 'InterviewRoom', params: { id } });
};

// 【核心修复#2】修正 handleAbandon 函数的逻辑
const handleAbandon = async () => {
    try {
        await abandonUnfinishedInterviewApi();
        ElMessage.success('面试已成功放弃！');
        // 重新获取列表以更新状态
        fetchHistory(); 
    } catch (error) {
        ElMessage.error('操作失败，请稍后重试。');
    }
};

const statusText = (status: string) => ({ running: '进行中', finished: '已完成', canceled: '已取消' }[status] || '未知');
const statusTagType = (status: string) => ({ running: 'primary', finished: 'success', canceled: 'info' }[status] || 'info');
</script>

<style scoped>
.page-container {
  padding: 20px;
}
.page-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>