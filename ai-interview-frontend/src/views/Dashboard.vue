<template>
  <div class="page-container" v-loading="jobStore.isLoading">
    <div v-if="!jobStore.isLoading && jobStore.industriesWithJobs.length > 0">
      <el-tabs v-model="jobStore.selectedIndustryId" class="job-tabs">
        <el-tab-pane label="所有行业" name="all"></el-tab-pane>
        <el-tab-pane
          v-for="industry in jobStore.industriesWithJobs"
          :key="industry.id"
          :label="industry.name"
          :name="String(industry.id)"
        ></el-tab-pane>
      </el-tabs>

      <div v-for="industry in jobStore.filteredIndustries" :key="industry.id" class="industry-section">
        <h2>{{ industry.name }}</h2>
        <el-row :gutter="20">
          <el-col :span="6" v-for="job in industry.job_positions" :key="job.id">
            <el-card shadow="hover" class="job-card" @click="openDialog(job.name)">
              <div class="job-card-content">
                <h3>{{ job.name }}</h3>
                <p>{{ job.description }}</p>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </div>
    <el-empty v-else-if="!jobStore.isLoading" description="暂无岗位信息"></el-empty>

    <el-dialog v-model="dialogVisible" title="开始面试前设置" width="600px">
      <p>为本次 <strong>{{ selectedJob }}</strong> 岗位面试选择一份简历：</p>

      <el-table
        :data="selectableResumes"
        highlight-current-row
        @current-change="handleResumeSelection"
        v-loading="isResumesLoading"
        max-height="250px"
      >
        <el-table-column property="title" label="简历标题"></el-table-column>
        <el-table-column label="更新时间">
          <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
      </el-table>
      <p v-if="!isResumesLoading && selectableResumes.length === 0" class="empty-tip">
        您还没有可用于面试的简历，请先到 <router-link to="/dashboard/resumes">简历中心</router-link> 上传或创建。
      </p>

      <el-divider />

      <div class="setting-item">
        <span>设置面试问题数量:</span>
        <el-input-number v-model="questionCount" :min="3" :max="10" />
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="startInterview"
          :disabled="!selectedResumeId"
          :loading="isStarting"
        >
          {{ isStarting ? '正在开启...' : '开始面试' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useJobStore } from '@/store/modules/job';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
import { startInterviewApi } from '@/api/modules/interview';
import { ElMessage } from 'element-plus';
import { formatDate } from '@/utils/format';

const router = useRouter();
const jobStore = useJobStore();

const dialogVisible = ref(false);
const selectedJob = ref('');
const questionCount = ref(5);

const allResumes = ref<ResumeItem[]>([]);
const isResumesLoading = ref(false);
const selectedResumeId = ref<number | null>(null);
const isStarting = ref(false);

const selectableResumes = computed(() => {
  const usableStatus = ['parsed', 'draft', 'published'];
  return allResumes.value.filter(r => usableStatus.includes(r.status));
});

const fetchAllResumes = async () => {
  isResumesLoading.value = true;
  try {
    allResumes.value = await getResumeListApi();
  } catch (error) {
    ElMessage.error('加载简历列表失败');
  } finally {
    isResumesLoading.value = false;
  }
};

const openDialog = (jobName: string) => {
  selectedJob.value = jobName;
  dialogVisible.value = true;
  fetchAllResumes();
};

const handleResumeSelection = (selectedRow: ResumeItem | null) => {
  selectedResumeId.value = selectedRow ? selectedRow.id : null;
};

const startInterview = async () => {
  if (!selectedResumeId.value) {
    ElMessage.warning('请选择一份用于面试的简历');
    return;
  }
  isStarting.value = true;
  try {
    const session = await startInterviewApi({
      job_position: selectedJob.value,
      resume_id: selectedResumeId.value,
      question_count: questionCount.value,
    });
    router.push({ name: 'InterviewRoom', params: { id: session.id } });
  } catch (error) {
    ElMessage.error('开启面试失败，请稍后再试');
  } finally {
    isStarting.value = false;
    dialogVisible.value = false;
  }
};

onMounted(() => {
  jobStore.fetchIndustries();
});
</script>

<style scoped>
/* 样式保持不变 */
</style>