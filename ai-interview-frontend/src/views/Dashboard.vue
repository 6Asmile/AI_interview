<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { 
  ElMessage, ElDialog, ElRadio, ElTable, ElTableColumn, ElPagination, ElButton, 
  ElRow, ElCol, ElRadioGroup, ElSlider, ElInputNumber, ElEmpty, ElSwitch
} from 'element-plus';
import { useJobStore } from '@/store/modules/job';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
// 【核心修正】从 interview.ts 导入 StartInterviewData 类型
import { startInterviewApi, type StartInterviewData } from '@/api/modules/interview';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const jobStore = useJobStore();

// --- 岗位选择相关状态 ---
const selectedIndustryId = ref<number | 'all'>('all');
// 【核心修正】将状态的 null 类型改为 undefined，以匹配 Element Plus 组件的要求
const selectedJobId = ref<number | undefined>(undefined);

const filteredJobs = computed(() => {
  if (selectedIndustryId.value === 'all') {
    return jobStore.industriesWithJobs.flatMap(industry => industry.job_positions);
  }
  const industry = jobStore.industriesWithJobs.find(i => i.id === selectedIndustryId.value);
  return industry ? industry.job_positions : [];
});

const selectedJob = computed(() => {
  return filteredJobs.value.find(job => job.id === selectedJobId.value) || null;
});

watch(filteredJobs, (newJobs) => {
  if (selectedJobId.value && !newJobs.some(job => job.id === selectedJobId.value)) {
    selectedJobId.value = undefined;
  }
});


// --- 开始面试面板相关状态 ---
const startDialogVisible = ref(false);
const isStarting = ref(false);
// 【核心修正】将状态的 null 类型改为 undefined，以匹配 Element Plus 组件的要求
const selectedResumeId = ref<number | undefined>(undefined);
const questionCount = ref(5);
const recordingEnabled = ref(false);
const resumes = ref<ResumeItem[]>([]);
const isLoadingResumes = ref(false);
const resumePagination = ref({
  currentPage: 1,
  pageSize: 5,
  total: 0,
});

// --- 数据获取 ---
onMounted(() => {
  jobStore.fetchIndustries();
});

const fetchResumes = async () => {
  isLoadingResumes.value = true;
  try {
    const params = { page: resumePagination.value.currentPage, page_size: resumePagination.value.pageSize };
    const response = await getResumeListApi(params);
    resumes.value = response.results;
    resumePagination.value.total = response.count;
    if (!selectedResumeId.value && resumes.value.length > 0) {
       selectedResumeId.value = resumes.value[0].id;
    }
  } catch (error) {
    ElMessage.error('简历列表加载失败');
  } finally {
    isLoadingResumes.value = false;
  }
};

// --- 事件处理 ---
const handleStartClick = () => {
  fetchResumes();
  startDialogVisible.value = true;
};

const handleResumePageChange = (page: number) => {
  resumePagination.value.currentPage = page;
  selectedResumeId.value = undefined; 
  fetchResumes();
};

const handleStartInterview = async () => {
  if (!selectedJob.value) return;
  isStarting.value = true;
  try {
    const payload: StartInterviewData = {
      job_position: selectedJob.value.name,
      question_count: questionCount.value,
      recording_enabled: recordingEnabled.value,
    };
    if (selectedResumeId.value) {
      payload.resume_id = selectedResumeId.value;
    }

    const session = await startInterviewApi(payload);
    ElMessage.success('面试已开启，正在进入房间...');
    router.push({ name: 'InterviewRoom', params: { id: session.id } });
  } catch (error) {
  } finally {
    isStarting.value = false;
  }
};
</script>

<template>
  <div class="dashboard-shell">
    <div class="dashboard-intro">
      <div>
        <p class="intro-kicker">AI Mock Interview</p>
        <h1>选择岗位，快速进入一场更真实的模拟面试</h1>
        <p class="intro-copy">我们提供覆盖多个行业的精选岗位和智能面试设置，助你高效准备面试，提升表现。</p>
      </div>
      <div class="intro-stats">
        <div class="intro-stat">
          <span class="stat-label">可选行业</span>
          <strong>{{ jobStore.industriesWithJobs.length || 0 }}</strong>
        </div>
        <div class="intro-stat">
          <span class="stat-label">题目数量</span>
          <strong>{{ questionCount }}</strong>
        </div>
      </div>
    </div>

    <el-row :gutter="24" class="dashboard-grid">
      <!-- 左侧：岗位选择 -->
      <el-col :span="16">
        <div class="panel job-selection-panel">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">Job Selection</p>
              <h3>选择面试岗位</h3>
            </div>
            <span class="panel-meta">{{ filteredJobs.length }} 个岗位</span>
          </div>
          <div class="panel-body">
            <div class="industry-tabs">
              <span :class="{ active: selectedIndustryId === 'all' }" @click="selectedIndustryId = 'all'">所有行业</span>
              <span
                v-for="industry in jobStore.industriesWithJobs"
                :key="industry.id"
                :class="{ active: selectedIndustryId === industry.id }"
                @click="selectedIndustryId = industry.id"
              >
                {{ industry.name }}
              </span>
            </div>
            <div class="job-list">
              <el-radio-group v-model="selectedJobId">
                <el-radio
                  v-for="job in filteredJobs"
                  :key="job.id"
                  :label="job.id"
                  border
                  class="job-radio-item"
                >
                  <div class="job-card-copy">
                    <span class="job-name">{{ job.name }}</span>
                    <span class="job-desc">{{ job.description }}</span>
                  </div>
                </el-radio>
              </el-radio-group>
              <el-empty v-if="!filteredJobs.length" description="该行业下暂无岗位" />
            </div>
          </div>
        </div>
      </el-col>
      <!-- 右侧：开始面试 -->
      <el-col :span="8">
        <div class="panel start-panel">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">Interview Setup</p>
              <h3>开始面试</h3>
            </div>
          </div>
          <div class="panel-body">
            <div class="selected-job-info">
              <p>已选岗位</p>
              <h4 v-if="selectedJob">{{ selectedJob.name }}</h4>
              <p v-else class="placeholder-text">请从左侧选择岗位</p>
              <div class="quick-badges">
                <span class="quick-badge">题量 {{ questionCount }}</span>
                <span class="quick-badge">{{ recordingEnabled ? '已开启录像' : '未开启录像' }}</span>
              </div>
            </div>
            <div class="resume-selection">
              <p>为本次面试选择一份简历 (可选)</p>
              <div class="resume-box" @click="handleStartClick">
                <div v-if="!resumes.length">暂无可用简历。<br><span class="link-text">点击选择或创建</span></div>
                <div v-else>{{ resumes.find(r => r.id === selectedResumeId)?.title || '点击选择简历' }}</div>
              </div>
            </div>
            <div class="question-count-setting">
               <p>设置面试问题数量</p>
               <div class="slider-wrapper">
                 <el-slider v-model="questionCount" :min="3" :max="10" show-stops />
                 <el-input-number v-model="questionCount" :min="3" :max="10" controls-position="right" size="small" />
               </div>
            </div>
            <div class="recording-setting">
              <p>开启面试录像</p>
              <div class="recording-switch-wrapper">
                <el-switch v-model="recordingEnabled" active-text="录制面试过程" inactive-text="不录制" />
              </div>
              <p class="recording-hint">开启后将录制您的面试视频，可在面试后查看回放</p>
            </div>
            <el-button
              type="primary"
              size="large"
              class="start-button"
              :disabled="!selectedJobId"
              @click="handleStartInterview"
              :loading="isStarting"
            >
              {{ isStarting ? '正在开启...' : '开始面试' }}
            </el-button>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 简历选择对话框 -->
    <el-dialog v-model="startDialogVisible" title="选择简历" width="50%" class="resume-dialog">
      <el-table :data="resumes" v-loading="isLoadingResumes" highlight-current-row>
        <el-table-column width="55">
          <template #default="scope">
            <!-- 【核心修正】v-model 绑定现在是类型安全的 -->
            <el-radio :label="scope.row.id" v-model="selectedResumeId" @change="startDialogVisible = false">&nbsp;</el-radio>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="简历标题" />
        <el-table-column label="最后更新">
          <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
        </el-table-column>
         <template #empty>
            <el-empty description="暂无可用简历。">
              <el-button type="primary" @click="router.push({ name: 'ResumeManagement' })">前往简历中心创建</el-button>
            </el-empty>
          </template>
      </el-table>
      <div class="pagination-container" v-if="resumePagination.total > resumePagination.pageSize">
        <el-pagination small background layout="prev, pager, next" :total="resumePagination.total" :page-size="resumePagination.pageSize" v-model:current-page="resumePagination.currentPage" @current-change="handleResumePageChange" />
      </div>
       <template #footer>
        <span class="dialog-footer">
          <el-button @click="startDialogVisible = false">关闭</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.dashboard-shell {
  min-height: calc(100vh - 60px);
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(76, 146, 255, 0.14), transparent 28%),
    radial-gradient(circle at top right, rgba(26, 188, 156, 0.12), transparent 24%),
    linear-gradient(180deg, #f7faff 0%, #f2f5fb 100%);
}

.dashboard-intro {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
  padding: 28px 30px;
  border: 1px solid rgba(187, 202, 231, 0.6);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 45px rgba(57, 84, 126, 0.08);
  backdrop-filter: blur(14px);
}

.intro-kicker,
.panel-kicker {
  margin: 0 0 8px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.dashboard-intro h1 {
  margin: 0 0 10px;
  color: #1d2a44;
  font-size: 30px;
  line-height: 1.2;
}

.intro-copy {
  margin: 0;
  max-width: 720px;
  color: #60708f;
  line-height: 1.7;
}

.intro-stats {
  display: flex;
  gap: 14px;
}

.intro-stat {
  min-width: 128px;
  padding: 16px 18px;
  border-radius: 20px;
  background: linear-gradient(135deg, #eff5ff 0%, #ffffff 100%);
  border: 1px solid #dbe7fb;
  text-align: left;
}

.stat-label {
  display: block;
  margin-bottom: 8px;
  color: #7c8ca8;
  font-size: 12px;
}

.intro-stat strong {
  color: #1c2d52;
  font-size: 24px;
}

.dashboard-grid {
  align-items: stretch;
}

.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid rgba(203, 214, 232, 0.85);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 24px 50px rgba(45, 70, 115, 0.08);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid rgba(225, 232, 244, 0.9);
}

.panel-header h3 {
  margin: 0;
  color: #1b2b4b;
  font-size: 22px;
  font-weight: 700;
}

.panel-meta {
  padding: 8px 12px;
  border-radius: 999px;
  background: #eef4ff;
  color: #4b6ca7;
  font-size: 12px;
  font-weight: 600;
}

.panel-body {
  flex-grow: 1;
  padding: 24px;
  overflow-y: auto;
}

.job-selection-panel .panel-body,
.start-panel .panel-body {
  display: flex;
  flex-direction: column;
}

.industry-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}

.industry-tabs span {
  padding: 10px 16px;
  border: 1px solid #dbe4f2;
  border-radius: 999px;
  background: #fff;
  color: #60708f;
  cursor: pointer;
  transition: all 0.22s ease;
}

.industry-tabs span:hover,
.industry-tabs span.active {
  border-color: #87aff8;
  background: linear-gradient(135deg, #edf4ff 0%, #dce9ff 100%);
  color: #2756a8;
  box-shadow: 0 10px 20px rgba(64, 123, 255, 0.12);
}

.job-list {
  flex-grow: 1;
  padding-right: 6px;
  overflow-y: auto;
}

.job-radio-item {
  width: 100%;
  height: auto;
  margin: 0 0 12px !important;
  padding: 0 !important;
  border: 1px solid #dbe4f2 !important;
  border-radius: 20px !important;
  background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.job-radio-item:hover {
  transform: translateY(-2px);
  border-color: #9ab8f2 !important;
  box-shadow: 0 18px 30px rgba(61, 95, 153, 0.08);
}

.job-radio-item :deep(.el-radio__input) {
  margin-top: 4px;
}

.job-radio-item :deep(.el-radio__label) {
  width: 100%;
  padding: 18px 20px 18px 0;
}

.job-card-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.job-name {
  color: #1f3152;
  font-size: 16px;
  font-weight: 700;
}

.job-desc {
  color: #6f7d94;
  font-size: 13px;
  line-height: 1.6;
  white-space: normal;
}

.selected-job-info,
.resume-selection,
.question-count-setting,
.recording-setting {
  margin-bottom: 22px;
}

.selected-job-info {
  padding: 20px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1f5fd8 0%, #5c9dff 100%);
  color: #fff;
  box-shadow: 0 20px 35px rgba(46, 101, 194, 0.24);
}

.selected-job-info p,
.resume-selection p,
.question-count-setting p,
.recording-setting p {
  margin: 0 0 8px;
  font-size: 14px;
  color: inherit;
}

.selected-job-info h4 {
  margin: 0;
  font-size: 30px;
  line-height: 1.2;
}

.placeholder-text {
  color: rgba(255, 255, 255, 0.75);
}

.quick-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}

.quick-badge {
  padding: 7px 10px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  font-size: 12px;
}

.resume-selection,
.question-count-setting,
.recording-setting {
  padding: 18px;
  border: 1px solid #e4ebf8;
  border-radius: 22px;
  background: #fbfcff;
}

.resume-selection p,
.question-count-setting p,
.recording-setting p {
  color: #576884;
}

.resume-box {
  padding: 18px;
  border: 1px dashed #9eb8e9;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(238, 245, 255, 0.9) 0%, rgba(255, 255, 255, 0.95) 100%);
  color: #47608e;
  text-align: center;
  cursor: pointer;
  transition: all 0.22s ease;
}

.resume-box:hover {
  border-color: #5f90eb;
  color: #2654a6;
  transform: translateY(-1px);
}

.link-text {
  color: #2c69d1;
  font-weight: 600;
}

.slider-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
}

.recording-switch-wrapper {
  display: flex;
  align-items: center;
}

.recording-hint {
  margin-top: 8px !important;
  color: #8b97ab !important;
  font-size: 12px !important;
  line-height: 1.6;
}

.start-button {
  width: 100%;
  min-height: 52px;
  margin-top: auto;
  border: none;
  border-radius: 18px;
  background: linear-gradient(135deg, #255fd2 0%, #66a2ff 100%);
  box-shadow: 0 18px 30px rgba(37, 95, 210, 0.22);
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

:deep(.el-radio.is-bordered.is-checked) {
  border-color: #5f8fe7 !important;
  background: linear-gradient(180deg, #f7fbff 0%, #eef5ff 100%);
  box-shadow: inset 0 0 0 1px rgba(95, 143, 231, 0.15);
}

:deep(.el-dialog.resume-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

:deep(.resume-dialog .el-dialog__header) {
  padding: 22px 24px 18px;
  margin-right: 0;
  border-bottom: 1px solid #edf1f8;
}

:deep(.resume-dialog .el-dialog__body) {
  padding: 20px 24px 24px;
}

@media (max-width: 1200px) {
  .dashboard-intro {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 768px) {
  .dashboard-shell {
    padding: 16px;
  }

  .dashboard-intro {
    padding: 22px 20px;
  }

  .dashboard-intro h1 {
    font-size: 24px;
  }

  .intro-stats {
    width: 100%;
  }

  .intro-stat {
    flex: 1;
  }

  .panel-body {
    padding: 18px;
  }

  .slider-wrapper {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
