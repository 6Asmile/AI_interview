<!-- src/views/Dashboard.vue -->
<template>
  <div class="dashboard-container">
    <el-row :gutter="24">
      <!-- Left Panel: Job Market -->
      <el-col :span="16">
        <el-card class="job-market-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>选择面试岗位</span>
            </div>
          </template>
          
          <div v-loading="jobStore.isLoading" class="job-market-content">
            <el-tabs v-model="jobStore.selectedIndustryId" tab-position="left" class="industry-tabs">
              <el-tab-pane label="所有行业" name="all" />
              <el-tab-pane
                v-for="industry in jobStore.industriesWithJobs"
                :key="industry.id"
                :label="industry.name"
                :name="String(industry.id)"
              />
            </el-tabs>
            
            <div class="job-list-container">
              <div v-if="jobStore.filteredIndustries.length > 0">
                <div v-for="industry in jobStore.filteredIndustries" :key="industry.id" class="industry-group">
                  <h3 class="industry-name">{{ industry.name }}</h3>
                  <div class="job-items-grid">
                    <div
                      v-for="job in industry.job_positions"
                      :key="job.id"
                      class="job-item"
                      :class="{ 'is-selected': selectedJob === job.name }"
                      @click="selectJob(job.name)"
                    >
                      <p class="job-name">{{ job.name }}</p>
                      <p class="job-description">{{ job.description }}</p>
                    </div>
                  </div>
                </div>
              </div>
              <el-empty v-else description="该行业下暂无岗位" />
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Right Panel: Interview Configuration -->
      <el-col :span="8">
        <el-card class="config-card" shadow="never">
           <template #header>
            <div class="card-header">
              <span>开始面试</span>
            </div>
          </template>
          
          <el-form label-position="top">
            <el-form-item label="已选岗位">
              <el-tag v-if="selectedJob" type="primary" size="large" effect="light" class="selected-job-tag">
                {{ selectedJob }}
              </el-tag>
              <span v-else class="placeholder-text">请从左侧选择岗位</span>
            </el-form-item>

            <el-divider />

            <el-form-item :label="`为本次面试选择一份简历（可选）`">
              <div class="resume-selection">
                <el-table 
                  :data="resumeList" 
                  @row-click="selectResume" 
                  highlight-current-row 
                  :show-header="false"
                  style="width: 100%;"
                  class="resume-table"
                  v-if="resumeList.length > 0"
                >
                  <el-table-column prop="title" />
                  <el-table-column width="140" align="right">
                    <template #default="scope">
                      <span class="update-time">{{ formatDateTime(scope.row.updated_at, '') }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-else class="no-resume-tip">
                  <p>暂无可用简历。</p>
                  <router-link to="/dashboard/resumes">
                    <el-button type="primary" link>前往简历中心创建</el-button>
                  </router-link>
                </div>
              </div>
            </el-form-item>
            
            <el-divider />

            <el-form-item label="设置面试问题数量">
              <el-slider v-model="questionCount" :min="3" :max="10" show-input />
            </el-form-item>
            
            <el-button
              type="primary"
              size="large"
              @click="handleStartInterview"
              :disabled="!selectedJob"
              :loading="isStarting"
              class="start-button"
            >
              {{ isStarting ? '正在开启...' : '开始面试' }}
            </el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useJobStore } from '@/store/modules/job';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
import { startInterviewApi } from '@/api/modules/interview';
import { ElMessage } from 'element-plus';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const jobStore = useJobStore();

const resumeList = ref<ResumeItem[]>([]);
const selectedJob = ref('');
const selectedResume = ref<ResumeItem | null>(null);
const questionCount = ref(5);
const isStarting = ref(false);

onMounted(async () => {
  // 并行获取数据，提升加载速度
  await Promise.all([
    jobStore.fetchIndustries(),
    fetchResumes()
  ]);
});

async function fetchResumes() {
    try {
        resumeList.value = await getResumeListApi();
    } catch (error) {
        ElMessage.error('加载简历列表失败');
    }
}

const selectJob = (jobName: string) => {
  selectedJob.value = jobName;
};

const selectResume = (row: ResumeItem) => {
  // 实现点击同一行取消选择的功能
  if (selectedResume.value?.id === row.id) {
    selectedResume.value = null;
    // 需要手动清除 el-table 的选中高亮
    // 这是 el-table 的一个特性，需要一些技巧来处理
  } else {
    selectedResume.value = row;
  }
};

const handleStartInterview = async () => {
  if (!selectedJob.value) {
    ElMessage.warning('请先选择一个面试岗位');
    return;
  }
  isStarting.value = true;
  try {
    const response = await startInterviewApi({
      job_position: selectedJob.value,
      resume_id: selectedResume.value?.id,
      question_count: questionCount.value
    });
    ElMessage.success('面试开启成功，即将进入面试房间...');
    router.push({ name: 'InterviewRoom', params: { id: response.id } });
  } catch (error) {
    // 错误信息已由 axios 拦截器统一处理
  } finally {
    isStarting.value = false;
  }
};
</script>

<style scoped>
.dashboard-container {
  padding: 24px;
  background-color: #f7f8fa;
  min-height: calc(100vh - 60px); /* 假设导航栏高度为 60px */
}

.card-header {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.job-market-card .job-market-content {
  display: flex;
}

.industry-tabs {
  min-width: 120px;
  flex-shrink: 0;
  margin-right: 24px;
}

.job-list-container {
  flex-grow: 1;
  height: 60vh;
  overflow-y: auto;
  padding-right: 10px; /* for scrollbar */
}

.industry-group {
  margin-bottom: 24px;
}
.industry-name {
  font-size: 14px;
  color: #666;
  margin-bottom: 16px;
}

.job-items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.job-item {
  border: 1px solid #e8eaf0;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  background-color: #fff;
}

.job-item:hover {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.job-item.is-selected {
  border-color: #409eff;
  background-color: #f0f7ff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.1);
}

.job-name {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}

.job-description {
  font-size: 13px;
  color: #888;
  line-height: 1.5;
}

.config-card {
  position: sticky;
  top: 24px; /* 让配置卡片在滚动时吸顶 */
}

.selected-job-tag {
  width: 100%;
  justify-content: center;
  font-size: 14px;
}

.placeholder-text {
  color: #a8abb2;
  font-size: 14px;
}

.resume-selection {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 8px;
  min-height: 100px;
}

.resume-table {
  --el-table-border-color: transparent;
  --el-table-header-bg-color: transparent;
}

.resume-table :deep(.el-table__row) {
  cursor: pointer;
}

.update-time {
  font-size: 12px;
  color: #999;
}

.no-resume-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  height: 100%;
  color: #999;
  font-size: 14px;
}
.no-resume-tip p {
  margin: 0;
}

.start-button {
  width: 100%;
}
</style>