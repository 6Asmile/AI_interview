<template>
  <div class="page-container dashboard-container">
    <div class="hero-section">
      <h1 class="title">选择面试岗位</h1>
      <p class="subtitle">请选择您的目标岗位，开启与专属AI面试官的对话</p>
    </div>
    <div class="industry-nav-wrapper">
      <el-menu :default-active="activeIndustryId" class="industry-menu" mode="horizontal" @select="handleIndustrySelect">
        <el-menu-item index="all">所有行业</el-menu-item>
        <el-menu-item v-for="industry in industriesWithJobs" :key="industry.id" :index="String(industry.id)">
          {{ industry.name }}
        </el-menu-item>
      </el-menu>
    </div>
    <el-skeleton :rows="10" animated v-if="loadingJobs" />
    <div v-if="!loadingJobs" class="industry-sections">
      <section v-for="industry in filteredIndustries" :key="industry.id" class="industry-section">
        <h2 class="industry-title">{{ industry.name }}</h2>
        <div class="job-grid">
          <div
            v-for="job in industry.job_positions"
            :key="job.id"
            class="job-card"
            @click="handleSelectJob(job.name)"
          >
            <div class="job-icon" v-html="job.icon_svg || defaultIcon"></div>
            <h3 class="job-title">{{ job.name }}</h3>
            <p class="job-description">{{ job.description }}</p>
          </div>
        </div>
      </section>
      <el-empty v-if="filteredIndustries.length === 0" description="该行业下暂无岗位" />
    </div>
    <el-dialog v-model="dialogVisible" title="开始面试前设置" width="600px">
      <div class="resume-selector">
        <p>为本次 **{{ selectedJob }}** 岗位面试选择一份简历：</p>
        <el-table :data="resumeList" v-loading="resumesLoading" highlight-current-row @current-change="handleResumeSelectionChange" style="width: 100%; margin-top: 20px" empty-text="您还没有上传简历">
          <el-table-column prop="title" label="简历标题" />
          <el-table-column prop="created_at" label="上传时间" width="180">
             <template #default="scope">{{ new Date(scope.row.created_at).toLocaleString() }}</template>
          </el-table-column>
        </el-table>
        <div class="question-count-setter">
          <p>设置面试问题数量:</p>
          <el-input-number v-model="questionCount" :min="3" :max="10" />
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleStartInterview(false)" :disabled="!selectedResumeId">开始面试</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElLoading, ElMessageBox } from 'element-plus';
import { startInterviewApi, checkUnfinishedInterviewApi, abandonUnfinishedInterviewApi } from '@/api/modules/interview';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
import { useJobStore } from '@/store/modules/job';

const router = useRouter();
const jobStore = useJobStore();

const dialogVisible = ref(false);
const resumesLoading = ref(false);
const loadingJobs = computed(() => jobStore.isLoading);
const selectedJob = ref('');
const resumeList = ref<ResumeItem[]>([]);
const selectedResumeId = ref<number | null>(null);
const questionCount = ref(5);
const industriesWithJobs = computed(() => jobStore.industriesWithJobs);
const activeIndustryId = computed(() => jobStore.selectedIndustryId);
const filteredIndustries = computed(() => jobStore.filteredIndustries);

const defaultIcon = `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M160 832h704a32 32 0 1 1 0 64H160a32 32 0 1 1 0-64zm384-255.872L862.592 257.536a32 32 0 0 0-45.184-45.184L544 484.8V128a32 32 0 0 0-64 0v356.8l-273.408-272.448a32 32 0 0 0-45.184 45.184L544 576.128z"></path></svg>`;

onMounted(() => {
  jobStore.fetchIndustries();
  checkAndResumeInterview();
});

const handleIndustrySelect = (index: string) => {
  jobStore.selectIndustry(index);
};

const handleSelectJob = async (jobTitle: string) => {
  selectedJob.value = jobTitle;
  dialogVisible.value = true;
  resumesLoading.value = true;
  try {
    const res = await getResumeListApi();
    resumeList.value = res.filter(r => r.status === 'parsed');
    if (resumeList.value.length === 0) {
      ElMessage.warning('您还没有已成功解析的简历。');
    }
  } catch (error) {
    console.error('获取简历列表失败', error);
  } finally {
    resumesLoading.value = false;
  }
};

const handleResumeSelectionChange = (currentRow: ResumeItem | undefined) => {
  if (currentRow) {
    selectedResumeId.value = currentRow.id;
  } else {
    selectedResumeId.value = null;
  }
};

const handleStartInterview = async (force: boolean = false) => {
  if (!selectedResumeId.value) {
    ElMessage.warning('请选择一份简历');
    return;
  }
  
  const loadingInstance = ElLoading.service({
    lock: true,
    text: 'AI面试官正在生成第一个问题...',
    background: 'rgba(0, 0, 0, 0.7)',
  });
  
  try {
    const sessionData = await startInterviewApi({
      job_position: selectedJob.value,
      resume_id: selectedResumeId.value,
      question_count: questionCount.value,
    }, force);
    
    dialogVisible.value = false;
    
    await router.push({ name: 'InterviewRoom', params: { id: sessionData.id } });

  } catch (error) {
    const axiosError = error as any;
    if (axiosError.response && axiosError.response.status === 409) {
      ElMessageBox.confirm('您当前已有正在进行的面试。是否要放弃旧的面试，开始一场全新的面试？', '提示', {
        confirmButtonText: '开始新的',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        handleStartInterview(true);
      }).catch(() => {
        ElMessage.info('已取消操作。');
      });
    } else { 
      console.error('开始面试失败', error);
      ElMessage.error('创建面试失败，请稍后再试');
    }
  } finally {
    loadingInstance.close();
  }
};

const checkAndResumeInterview = async () => {
  try {
    const res = await checkUnfinishedInterviewApi();
    if (res.has_unfinished && res.session_id) {
      ElMessageBox.confirm(`我们发现您有一个正在进行的 <strong>${res.job_position}</strong> 面试，是否要继续？`, '欢迎回来！', {
        confirmButtonText: '继续面试',
        cancelButtonText: '放弃',
        type: 'info',
        dangerouslyUseHTMLString: true,
      }).then(() => {
        router.push({ name: 'InterviewRoom', params: { id: res.session_id } });
      })
      .catch(async () => {
        const loading = ElLoading.service({ text: '正在放弃面试...' });
        try {
          await abandonUnfinishedInterviewApi();
          ElMessage.success('之前的面试已放弃。');
        } catch (abandonError) {
          ElMessage.error('放弃面试失败，请稍后再试。');
        } finally {
          loading.close();
        }
      });
    }
  } catch (error) {
    console.error("检查未完成面试失败", error);
  }
};
</script>

<style scoped>
.dashboard-container { padding: 20px 40px; }
.hero-section { text-align: center; margin-bottom: 40px; }
.title { font-size: 2.5rem; font-weight: 700; color: #333; margin-bottom: 1rem; }
.subtitle { font-size: 1.1rem; color: #666; }
.industry-nav-wrapper { margin-bottom: 40px; border-bottom: 1px solid #e4e7ed; display: flex; justify-content: center; }
.industry-menu { border-bottom: none !important; }
.industry-section { margin-bottom: 40px; }
.industry-title { font-size: 1.8rem; font-weight: 600; text-align: left; margin-bottom: 20px; padding-bottom: 10px; }
.job-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 2rem; }
.job-card { padding: 2rem; text-align: center; background-color: rgba(255, 255, 255, 0.7); border-radius: 16px; box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1); backdrop-filter: blur(4px); border: 1px solid rgba(255, 255, 255, 0.2); transition: all 0.3s ease; cursor: pointer; }
.job-card:hover { transform: translateY(-10px); box-shadow: 0 16px 32px 0 rgba(31, 38, 135, 0.15); }
.job-icon { margin-bottom: 1rem; color: #409EFF; width: 40px; height: 40px; display: inline-block; }
.job-title { font-size: 1.5rem; font-weight: 600; color: #333; margin-bottom: 0.5rem; }
.job-description { font-size: 1rem; color: #777; line-height: 1.5; }
.question-count-setter { margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 15px; }
</style>