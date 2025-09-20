<template>
  <div class="dashboard-container">
    <div class="hero-section">
      <h1 class="title">选择面试岗位</h1>
      <p class="subtitle">请选择您的目标岗位，开启与专属AI面试官的对话</p>
    </div>

    <div class="job-grid">
      <div
        v-for="job in jobPositions"
        :key="job.title"
        class="job-card"
        @click="handleSelectJob(job.title)"
      >
        <el-icon :size="40" class="job-icon"><component :is="job.icon" /></el-icon>
        <h3 class="job-title">{{ job.title }}</h3>
        <p class="job-description">{{ job.description }}</p>
      </div>
    </div>

    <!-- 改造：简历选择对话框 -->
    <el-dialog v-model="dialogVisible" title="开始面试前设置" width="600px">
      <div class="resume-selector">
        <p>为本次 **{{ selectedJob }}** 岗位面试选择一份简历：</p>
        <el-table
          :data="resumeList"
          v-loading="resumesLoading"
          highlight-current-row
          @current-change="handleResumeSelectionChange"
          style="width: 100%; margin-top: 20px"
          empty-text="您还没有上传简历，请先前往简历中心上传"
        >
          <el-table-column prop="title" label="简历标题" />
          <el-table-column prop="created_at" label="上传时间" width="180">
             <template #default="scope">
              {{ new Date(scope.row.created_at).toLocaleString() }}
            </template>
          </el-table-column>
        </el-table>
        
        <!-- 新增：问题数量设置 -->
        <div class="question-count-setter">
          <p>设置面试问题数量:</p>
          <el-input-number v-model="questionCount" :min="3" :max="10" />
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleStartInterview" :disabled="!selectedResumeId">
            开始面试
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElLoading } from 'element-plus';
import { startInterviewApi } from '@/api/modules/interview';
import { getResumeListApi, type ResumeItem } from '@/api/modules/resume';
import {
  Monitor,
  Platform,
  Opportunity,
  Aim,
  TrendCharts,
  DataAnalysis,
  Operation,
  Suitcase,
} from '@element-plus/icons-vue';

const router = useRouter();

const dialogVisible = ref(false);
const resumesLoading = ref(false);
const selectedJob = ref('');
const resumeList = ref<ResumeItem[]>([]);
const selectedResumeId = ref<number | null>(null);
const questionCount = ref(5); // 新增：问题数量，默认值为5

const handleSelectJob = async (jobTitle: string) => {
  selectedJob.value = jobTitle;
  dialogVisible.value = true;
  resumesLoading.value = true;
  try {
    const res = await getResumeListApi();
    resumeList.value = res.filter(r => r.status === 'parsed');
    if (resumeList.value.length === 0) {
      ElMessage.warning('您还没有已成功解析的简历，请先上传并确保解析成功。');
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

const handleStartInterview = async () => {
  if (!selectedResumeId.value) {
    ElMessage.warning('请选择一份简历');
    return;
  }
  const loadingInstance = ElLoading.service({
    lock: true,
    text: 'AI面试官正在阅读您的简历并准备问题...',
    background: 'rgba(0, 0, 0, 0.7)',
  });
  try {
    const sessionData = await startInterviewApi({
      job_position: selectedJob.value,
      resume_id: selectedResumeId.value,
      question_count: questionCount.value, // 附带问题数量
    });
    dialogVisible.value = false;
    await router.push({ name: 'InterviewRoom', params: { id: sessionData.id } });
  } catch (error) {
    console.error('开始面试失败', error);
    ElMessage.error('创建面试失败，请稍后再试');
  } finally {
    loadingInstance.close();
  }
};

const jobPositions = ref([
  { title: '前端开发工程师', icon: Monitor, description: '负责网站和应用用户界面的设计、开发与优化。' },
  { title: '后端开发工程师', icon: Platform, description: '负责服务器程序、数据库和API的设计与开发。' },
  { title: '算法工程师', icon: Opportunity, description: '专注于设计、实现和优化解决特定问题的算法模型。' },
  { title: '人工智能工程师', icon: Aim, description: '负责机器学习模型的设计、训练、部署和维护。' },
  { title: '测试工程师', icon: TrendCharts, description: '负责产品的功能、性能和安全测试，保障质量。' },
  { title: '大数据工程师', icon: DataAnalysis, description: '负责大规模数据的采集、存储、处理和分析。' },
  { title: '运维工程师', icon: Operation, description: '负责系统的部署、监控、维护和自动化。' },
  { title: '产品经理', icon: Suitcase, description: '负责产品规划、需求分析和项目推进。' },
]);
</script>

<style scoped>
/* --- 样式保持不变，只为新元素追加样式 --- */
.dashboard-container { padding: 40px; text-align: center; }
.hero-section { margin-bottom: 60px; }
.title { font-size: 3rem; font-weight: 700; color: #333; margin-bottom: 1rem; }
.subtitle { font-size: 1.25rem; color: #666; }
.job-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 2rem; max-width: 1200px; margin: 0 auto; }
.job-card { padding: 2rem; background-color: rgba(255, 255, 255, 0.7); border-radius: 16px; box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1); backdrop-filter: blur(4px); border: 1px solid rgba(255, 255, 255, 0.2); transition: all 0.3s ease; cursor: pointer; }
.job-card:hover { transform: translateY(-10px); box-shadow: 0 16px 32px 0 rgba(31, 38, 135, 0.15); }
.job-icon { margin-bottom: 1rem; color: #409EFF; }
.job-title { font-size: 1.5rem; font-weight: 600; color: #333; margin-bottom: 0.5rem; }
.job-description { font-size: 1rem; color: #777; line-height: 1.5; }
/* 新增样式 */
.question-count-setter {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #eee;
  display: flex;
  align-items: center;
  gap: 15px;
}
</style>