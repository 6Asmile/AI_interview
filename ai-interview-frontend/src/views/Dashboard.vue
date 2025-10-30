<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { 
  ElMessage, ElDialog, ElRadio, ElTable, ElTableColumn, ElPagination, ElButton, 
  ElRow, ElCol, ElRadioGroup, ElSlider, ElInputNumber, ElEmpty
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
    // 【核心修正】构建一个符合 StartInterviewData 类型的 payload
    const payload: StartInterviewData = {
      job_position: selectedJob.value.name,
      question_count: questionCount.value,
    };
    // 只有当 resume_id 存在时（不为 undefined），才将其添加到 payload 中
    if (selectedResumeId.value) {
      payload.resume_id = selectedResumeId.value;
    }

    const session = await startInterviewApi(payload); // 传递修正后的 payload
    ElMessage.success('面试已开启，正在进入房间...');
    router.push({ name: 'InterviewRoom', params: { id: session.id } });
  } catch (error) {
    // request.ts 中已经处理了错误提示
  } finally {
    isStarting.value = false;
  }
};
</script>

<template>
  <div class="dashboard-container">
    <el-row :gutter="24">
      <!-- 左侧：岗位选择 -->
      <el-col :span="16">
        <div class="panel job-selection-panel">
          <div class="panel-header">
            <h3>选择面试岗位</h3>
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
                  <span class="job-name">{{ job.name }}</span>
                  <span class="job-desc">{{ job.description }}</span>
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
            <h3>开始面试</h3>
          </div>
          <div class="panel-body">
            <div class="selected-job-info">
              <p>已选岗位</p>
              <h4 v-if="selectedJob">{{ selectedJob.name }}</h4>
              <p v-else class="placeholder-text">请从左侧选择岗位</p>
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
    <el-dialog v-model="startDialogVisible" title="选择简历" width="50%">
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
/* 样式与上一版相同，无需修改 */
.dashboard-container{padding:24px;background-color:#f5f7fa;height:calc(100vh - 90px)}.panel{background-color:#fff;border-radius:8px;border:1px solid #e4e7ed;height:100%;display:flex;flex-direction:column}.panel-header{padding:16px 20px;border-bottom:1px solid #e4e7ed}.panel-header h3{margin:0;font-size:1.1rem}.panel-body{padding:20px;flex-grow:1;overflow-y:auto}.job-selection-panel .panel-body{display:flex;flex-direction:column}.industry-tabs{margin-bottom:16px;display:flex;flex-wrap:wrap;gap:16px}.industry-tabs span{padding:4px 12px;cursor:pointer;border-radius:4px;transition:all .2s ease}.industry-tabs span.active{background-color:#ecf5ff;color:#409eff;font-weight:500}.job-list{flex-grow:1;overflow-y:auto}.job-radio-item{width:100%;margin:8px 0!important;height:auto;padding:12px;display:flex}.job-radio-item .job-name{font-weight:500;color:#303133}.job-radio-item .job-desc{font-size:.8rem;color:#909399;margin-top:4px;white-space:normal}.start-panel .panel-body{display:flex;flex-direction:column}.selected-job-info,.resume-selection,.question-count-setting{margin-bottom:24px}.selected-job-info p,.resume-selection p,.question-count-setting p{margin:0 0 8px;color:#606266;font-size:.9rem}.selected-job-info h4{margin:0;font-size:1.5rem;color:#303133}.placeholder-text{color:#c0c4cc}.resume-box{border:1px dashed #dcdfe6;border-radius:4px;padding:16px;text-align:center;cursor:pointer;color:#606266;transition:border-color .2s,color .2s}.resume-box:hover{border-color:#409eff;color:#409eff}.link-text{color:#409eff}.slider-wrapper{display:flex;align-items:center;gap:16px}.start-button{width:100%;margin-top:auto}.pagination-container{display:flex;justify-content:center;margin-top:16px}
</style>