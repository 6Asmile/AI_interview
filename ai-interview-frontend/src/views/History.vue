<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElTag, ElButton, ElTabs, ElTabPane, ElPagination, ElDialog, ElProgress } from 'element-plus';
import { getInterviewHistoryApi, getAnalysisHistoryApi } from '@/api/modules/report';
import { abandonUnfinishedInterviewApi, getRecordingStatusApi, type InterviewSessionItem } from '@/api/modules/interview';
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

const videoDialogVisible = ref(false);
const currentRecordingStatus = ref<{
  has_recording: boolean;
  video_url: string | null;
  status: string | null;
  progress: number;
  error_message: string | null;
} | null>(null);
const isLoadingRecording = ref(false);

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

const handleAbandon = async (_sessionId: string) => {
  try {
    await ElMessageBox.confirm('确定要放弃这次进行中的面试吗？', '确认', { type: 'warning' });
    await abandonUnfinishedInterviewApi();
    ElMessage.success('面试已放弃');
    fetchInterviewHistory();
  } catch (error) {
    if (error !== 'cancel') ElMessage.info('操作已取消');
  }
};

const handleViewRecording = async (sessionId: string) => {
  isLoadingRecording.value = true;
  videoDialogVisible.value = true;
  currentRecordingStatus.value = null;
  
  try {
    const status = await getRecordingStatusApi(sessionId);
    currentRecordingStatus.value = status;
  } catch (error) {
    ElMessage.error('获取录像状态失败');
    videoDialogVisible.value = false;
  } finally {
    isLoadingRecording.value = false;
  }
};

const recordingStatusText = (status: string | null): string => {
  const statusMap: Record<string, string> = {
    'pending': '等待处理',
    'uploading': '上传中',
    'transcoding': '转码中',
    'completed': '已完成',
    'failed': '处理失败'
  };
  return status ? statusMap[status] || '未知' : '无录像';
};

const recordingStatusType = (status: string | null): 'success' | 'warning' | 'info' | 'danger' => {
  const typeMap: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    'pending': 'info',
    'uploading': 'warning',
    'transcoding': 'warning',
    'completed': 'success',
    'failed': 'danger'
  };
  return status ? typeMap[status] || 'info' : 'info';
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
              <el-button v-if="scope.row.status === 'finished' && scope.row.recording_enabled" size="small" type="info" @click="handleViewRecording(scope.row.id)">查看录像</el-button>
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
    
    <el-dialog v-model="videoDialogVisible" title="面试录像" width="600px">
      <div v-loading="isLoadingRecording">
        <div v-if="currentRecordingStatus">
          <div class="recording-info mb-4">
            <p class="mb-2">
              <span class="text-gray-500">录像状态：</span>
              <el-tag :type="recordingStatusType(currentRecordingStatus.status)" size="small">
                {{ recordingStatusText(currentRecordingStatus.status) }}
              </el-tag>
            </p>
            <p v-if="currentRecordingStatus.status === 'transcoding'" class="mb-2">
              <span class="text-gray-500">转码进度：</span>
              <el-progress :percentage="currentRecordingStatus.progress" :stroke-width="8" class="inline-progress" />
            </p>
            <p v-if="currentRecordingStatus.error_message" class="text-red-500 text-sm">
              错误信息：{{ currentRecordingStatus.error_message }}
            </p>
          </div>
          
          <div v-if="currentRecordingStatus.video_url" class="video-player">
            <video 
              :src="currentRecordingStatus.video_url" 
              controls 
              class="w-full rounded-lg"
              style="max-height: 400px;"
            />
          </div>
          
          <div v-else-if="!currentRecordingStatus.has_recording" class="text-center text-gray-400 py-8">
            该面试没有录像
          </div>
          
          <div v-else-if="currentRecordingStatus.status === 'pending'" class="text-center text-gray-400 py-8">
            录像正在等待处理，请稍后再试
          </div>
          
          <div v-else-if="currentRecordingStatus.status === 'uploading'" class="text-center py-8">
            <el-progress type="circle" :percentage="currentRecordingStatus.progress" />
            <p class="text-gray-500 mt-4">录像正在上传中...</p>
          </div>
          
          <div v-else-if="currentRecordingStatus.status === 'transcoding'" class="text-center py-8">
            <el-progress type="circle" :percentage="currentRecordingStatus.progress" />
            <p class="text-gray-500 mt-4">录像正在转码中...</p>
          </div>
          
          <div v-else-if="currentRecordingStatus.status === 'failed'" class="text-center text-red-500 py-8">
            录像处理失败
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="videoDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
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
.recording-info {
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;
}
.inline-progress {
  display: inline-flex;
  width: 200px;
  vertical-align: middle;
  margin-left: 8px;
}
.video-player {
  background-color: #000;
  border-radius: 8px;
  overflow: hidden;
}
</style>