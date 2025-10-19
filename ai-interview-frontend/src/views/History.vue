<!-- src/views/History.vue -->
<template>
  <div class="page-container">
    <el-card>
      <el-tabs v-model="activeTab">
        <!-- Tab 1: 面试记录 -->
        <el-tab-pane label="面试记录" name="interviews">
          <el-table :data="interviewHistory" v-loading="interviewLoading" style="width: 100%">
            <el-table-column prop="job_position" label="面试岗位" />
            <el-table-column label="状态" width="120">
              <template #default="scope">
                <el-tag :type="interviewStatusTag(scope.row.status)">{{ interviewStatusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="200">
              <template #default="scope">{{ formatDateTime(scope.row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="scope">
                <el-button v-if="scope.row.status === 'finished'" link type="primary" @click="viewInterviewReport(scope.row.id)">查看报告</el-button>
                <template v-if="scope.row.status === 'running'">
                  <el-button link type="success" @click="continueInterview(scope.row.id)">继续面试</el-button>
                  <el-popconfirm title="确定要放弃这场面试吗？" @confirm="handleAbandon">
                    <template #reference><el-button link type="danger">放弃面试</el-button></template>
                  </el-popconfirm>
                </template>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!interviewLoading && interviewHistory.length === 0" description="暂无面试记录" />
        </el-tab-pane>

        <!-- Tab 2: 分析报告 -->
        <el-tab-pane label="分析报告" name="analysis">
          <el-table :data="analysisHistory" v-loading="analysisLoading" style="width: 100%">
            <el-table-column label="关联简历">
                <template #default="scope">{{ getResumeTitle(scope.row.resume) }}</template>
            </el-table-column>
            <el-table-column prop="overall_score" label="匹配度得分" width="150" align="center" />
            <el-table-column label="分析时间" width="200">
              <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="scope">
                <el-button link type="primary" @click="viewAnalysisReport(scope.row.id)">查看详情</el-button>
              </template>
            </el-table-column>
          </el-table>
           <el-empty v-if="!analysisLoading && analysisHistory.length === 0" description="暂无分析报告记录" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getInterviewHistoryApi as getInterviewHistoryFromReportApi, getAnalysisHistoryApi, type ResumeAnalysisReportItem } from '@/api/modules/report';
import { abandonUnfinishedInterviewApi, type InterviewSessionItem } from '@/api/modules/interview';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
import { ElMessage, ElPopconfirm, ElTabs, ElTabPane, ElTable, ElTableColumn, ElTag, ElButton, ElCard, ElEmpty } from 'element-plus';
import { formatDateTime } from '@/utils/format';

// --- 【核心修复】定义 el-tag 的 type 联合类型 ---
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger';

const router = useRouter();
const activeTab = ref('interviews');
const interviewHistory = ref<InterviewSessionItem[]>([]);
const interviewLoading = ref(true);
const analysisHistory = ref<ResumeAnalysisReportItem[]>([]);
const analysisLoading = ref(true);
const resumeList = ref<ResumeItem[]>([]);

const fetchAllData = async () => {
  interviewLoading.value = true;
  analysisLoading.value = true;
  try {
    const [interviews, analyses, resumes] = await Promise.all([
      getInterviewHistoryFromReportApi(),
      getAnalysisHistoryApi(),
      getResumeListApi()
    ]);
    interviewHistory.value = interviews;
    analysisHistory.value = analyses;
    resumeList.value = resumes;
  } catch (error) {
    ElMessage.error('加载历史记录失败');
    console.error(error);
  } finally {
    interviewLoading.value = false;
    analysisLoading.value = false;
  }
};

onMounted(fetchAllData);

const viewInterviewReport = (id: string) => {
  router.push({ name: 'ReportDetail', params: { id } });
};

const continueInterview = (id: string) => {
  router.push({ name: 'InterviewRoom', params: { id } });
};

const handleAbandon = async () => {
    try {
        await abandonUnfinishedInterviewApi();
        ElMessage.success('面试已成功放弃！');
        fetchAllData();
    } catch (error) {
        ElMessage.error('操作失败，请稍后重试。');
    }
};

const interviewStatusText = (status: string): string => {
    const map: Record<string, string> = { running: '进行中', finished: '已完成', canceled: '已取消' };
    return map[status] || '未知';
};

// --- 【核心修复】为函数添加明确的返回类型 ---
const interviewStatusTag = (status: string): TagType => {
    const map: Record<string, TagType> = { running: 'primary', finished: 'success', canceled: 'info' };
    return map[status] || 'info';
};

const viewAnalysisReport = (reportId: string) => {
    router.push({ name: 'AnalysisReportDetail', params: { reportId } });
};

const getResumeTitle = (resumeId: number): string => {
    const resume = resumeList.value.find(r => r.id === resumeId);
    return resume ? resume.title : `简历 #${resumeId}`;
};
</script>

<style scoped>
.page-container { padding: 20px; }
.page-card-header { display: flex; justify-content: space-between; align-items: center; }
</style>