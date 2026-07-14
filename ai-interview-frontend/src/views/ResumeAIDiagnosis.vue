<template>
  <div class="diagnosis-page">
    <header class="page-header">
      <div>
        <h1>AI 简历诊断</h1>
        <p>分析只使用你确认过的简历版本和真实岗位 JD。</p>
      </div>
      <el-tag :type="asyncAvailable ? 'success' : 'danger'">
        {{ asyncAvailable ? '解析服务在线' : '解析服务未就绪' }}
      </el-tag>
    </header>

    <el-alert
      v-if="!asyncAvailable"
      type="warning"
      title="Celery Worker 未连接，文件解析任务不会执行。请先启动应用开发服务。"
      :closable="false"
      show-icon
    />

    <section class="workflow-section">
      <el-steps :active="activeStep" finish-status="success" simple>
        <el-step title="选择岗位" />
        <el-step title="解析简历" />
        <el-step title="确认并分析" />
      </el-steps>
    </section>

    <section v-if="activeStep === 0" class="form-section">
      <h2>诊断目标</h2>
      <el-radio-group v-model="jdMode">
        <el-radio-button value="target">求职工作台岗位</el-radio-button>
        <el-radio-button value="manual">粘贴真实 JD</el-radio-button>
      </el-radio-group>
      <el-select
        v-if="jdMode === 'target'"
        v-model="selectedTargetId"
        class="full-width"
        filterable
        placeholder="选择包含 JD 的目标岗位"
      >
        <el-option
          v-for="target in jobTargets"
          :key="target.id"
          :label="`${target.company_name} · ${target.position_name}`"
          :value="target.id"
          :disabled="!target.jd_text?.trim()"
        />
      </el-select>
      <el-input
        v-else
        v-model="jdText"
        type="textarea"
        :rows="8"
        placeholder="粘贴招聘方发布的完整岗位职责与任职要求"
      />

      <el-upload
        ref="uploadRef"
        class="resume-upload"
        drag
        action="#"
        :auto-upload="false"
        :limit="1"
        :on-change="handleFileChange"
        :on-exceed="handleExceed"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽 PDF 或 DOCX 到这里，或点击选择</div>
        <template #tip><div class="el-upload__tip">文件不超过 15MB，解析结果需要人工确认。</div></template>
      </el-upload>
      <el-button type="primary" :loading="uploading" :disabled="!canStart" @click="uploadAndParse">
        上传并开始解析
      </el-button>
    </section>

    <section v-else-if="activeStep === 1" class="processing-section">
      <el-icon class="is-loading" :size="42"><Loading /></el-icon>
      <h2>{{ importStatusText }}</h2>
      <p>任务编号 {{ importJob?.id }}。你可以离开页面，任务状态会保留。</p>
      <el-button v-if="importJob?.status === 'failed'" @click="retryImport">重新解析</el-button>
    </section>

    <section v-else class="review-section">
      <div class="review-heading">
        <div><h2>确认解析内容</h2><p>可以修正结构化内容；确认后会生成不可变简历版本。</p></div>
        <el-tag type="warning">等待人工确认</el-tag>
      </div>
      <el-input v-model="parsedJsonText" type="textarea" :rows="18" spellcheck="false" />
      <div class="actions">
        <el-button @click="resetWorkflow">重新上传</el-button>
        <el-button type="primary" :loading="analyzing" @click="confirmAndAnalyze">确认版本并生成诊断</el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, genFileId } from 'element-plus';
import type { UploadFile, UploadInstance, UploadProps, UploadRawFile } from 'element-plus';
import { Loading, UploadFilled } from '@element-plus/icons-vue';
import {
  confirmResumeImportApi,
  createResumeApi,
  getResumeImportApi,
  retryResumeImportApi,
  type ResumeImportJob,
} from '@/api/modules/resume';
import { analyzeResumeVersionApi } from '@/api/modules/resumeEditor';
import { getJobTargetsApi, type JobTarget } from '@/api/modules/career';
import { getSystemReadinessApi } from '@/api/modules/system';

const router = useRouter();
const uploadRef = ref<UploadInstance>();
const fileToUpload = ref<UploadFile | null>(null);
const activeStep = ref(0);
const uploading = ref(false);
const analyzing = ref(false);
const asyncAvailable = ref(false);
const jobTargets = ref<JobTarget[]>([]);
const selectedTargetId = ref<number>();
const jdMode = ref<'target' | 'manual'>('target');
const jdText = ref('');
const importJob = ref<ResumeImportJob | null>(null);
const parsedJsonText = ref('');

const selectedTarget = computed(() => jobTargets.value.find(item => item.id === selectedTargetId.value));
const hasRealJd = computed(() => jdMode.value === 'target' ? !!selectedTarget.value?.jd_text?.trim() : !!jdText.value.trim());
const canStart = computed(() => asyncAvailable.value && !!fileToUpload.value?.raw && hasRealJd.value && !uploading.value);
const importStatusText = computed(() => ({
  pending: '等待解析服务接收任务', processing: '正在解析简历', failed: '解析失败',
  review_required: '解析完成', confirmed: '已确认', canceled: '任务已取消',
}[importJob.value?.status || 'pending']));

onMounted(async () => {
  const [targetsResult, readinessResult] = await Promise.allSettled([getJobTargetsApi(), getSystemReadinessApi()]);
  if (targetsResult.status === 'fulfilled') jobTargets.value = targetsResult.value.filter(item => item.status === 'active');
  if (readinessResult.status === 'fulfilled') asyncAvailable.value = readinessResult.value.async_jobs_available;
});

const handleFileChange: UploadProps['onChange'] = (uploadFile, uploadFiles) => {
  const allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  if (!uploadFile.raw || !allowed.includes(uploadFile.raw.type) || (uploadFile.size || 0) > 15 * 1024 * 1024) {
    ElMessage.error('请选择不超过 15MB 的 PDF 或 DOCX 文件');
    uploadRef.value?.clearFiles();
    fileToUpload.value = null;
    return;
  }
  fileToUpload.value = uploadFiles.at(-1) || null;
};

const handleExceed: UploadProps['onExceed'] = (files) => {
  uploadRef.value?.clearFiles();
  const file = files[0] as UploadRawFile;
  file.uid = genFileId();
  uploadRef.value?.handleStart(file);
};

const wait = (milliseconds: number) => new Promise(resolve => window.setTimeout(resolve, milliseconds));

async function pollImport(jobId: number) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    importJob.value = await getResumeImportApi(jobId);
    if (importJob.value.status === 'review_required') {
      parsedJsonText.value = JSON.stringify(importJob.value.parsed_json || {}, null, 2);
      activeStep.value = 2;
      return;
    }
    if (importJob.value.status === 'failed' || importJob.value.status === 'canceled') return;
    await wait(2000);
  }
  ElMessage.warning('解析时间较长，任务会继续在后台运行');
}

async function uploadAndParse() {
  if (!fileToUpload.value?.raw || !hasRealJd.value) return;
  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append('file', fileToUpload.value.raw);
    formData.append('title', fileToUpload.value.name.replace(/\.[^/.]+$/, ''));
    const resume = await createResumeApi(formData);
    if (!resume.import_job) throw new Error('missing_import_job');
    importJob.value = resume.import_job;
    activeStep.value = 1;
    await pollImport(resume.import_job.id);
  } finally {
    uploading.value = false;
  }
}

async function retryImport() {
  if (!importJob.value) return;
  importJob.value = await retryResumeImportApi(importJob.value.id);
  await pollImport(importJob.value.id);
}

async function confirmAndAnalyze() {
  if (!importJob.value) return;
  analyzing.value = true;
  try {
    let resumeJson: Record<string, any>;
    try { resumeJson = JSON.parse(parsedJsonText.value); }
    catch { return ElMessage.error('结构化内容不是有效 JSON，请检查后重试'); }
    const version = await confirmResumeImportApi(importJob.value.id, resumeJson);
    const report = await analyzeResumeVersionApi({
      resume_version_id: version.id,
      job_target_id: jdMode.value === 'target' ? selectedTargetId.value : undefined,
      jd_text: jdMode.value === 'manual' ? jdText.value.trim() : undefined,
    });
    ElMessage.success('诊断已完成');
    await router.push({ name: 'AnalysisReportDetail', params: { reportId: report.id } });
  } finally {
    analyzing.value = false;
  }
}

function resetWorkflow() {
  activeStep.value = 0;
  importJob.value = null;
  parsedJsonText.value = '';
  fileToUpload.value = null;
  uploadRef.value?.clearFiles();
}
</script>

<style scoped>
.diagnosis-page { max-width: 980px; min-height: calc(100vh - 60px); margin: 0 auto; padding: 28px 24px 48px; }
.page-header, .review-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.page-header h1, h2 { margin: 0; color: #1f2937; letter-spacing: 0; }
.page-header p, .review-heading p, .processing-section p { margin: 8px 0 0; color: #667085; }
.workflow-section { margin: 22px 0; }
.form-section, .review-section, .processing-section { padding: 24px; border: 1px solid #dfe5ec; background: #fff; }
.form-section { display: grid; gap: 18px; }
.full-width { width: 100%; }
.resume-upload { margin-top: 4px; }
.processing-section { min-height: 320px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.review-heading { margin-bottom: 18px; }
.actions { justify-content: flex-end; margin-top: 18px; }
@media (max-width: 720px) { .diagnosis-page { padding: 18px 14px; } .page-header, .review-heading { align-items: flex-start; flex-direction: column; } }
</style>
