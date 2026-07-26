<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ArrowRight, DocumentAdd, UploadFilled } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox, type UploadFile, type UploadInstance } from 'element-plus';
import {
  createResumeV2Api,
  deleteResumeV2Api,
  getResumesV2Api,
  importResumeV2Api,
  type ResumeV2,
} from '@/api/modules/resume';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const resumes = ref<ResumeV2[]>([]);
const loading = ref(false);
const uploadVisible = ref(false);
const uploading = ref(false);
const uploadRef = ref<UploadInstance>();
const uploadFile = ref<UploadFile | null>(null);
const uploadTitle = ref('');

async function load() {
  loading.value = true;
  try {
    resumes.value = await getResumesV2Api();
  } finally {
    loading.value = false;
  }
}

async function createResume() {
  const title = await ElMessageBox.prompt('给这份简历起一个便于识别的名称。', '创建简历', {
    inputPlaceholder: '例如：后端工程师主简历',
    inputPattern: /\S+/,
    inputErrorMessage: '请输入简历名称',
  }).then(result => result.value).catch(() => '');
  if (!title) return;
  const resume = await createResumeV2Api({ title, status: 'draft', is_default: resumes.value.length === 0 });
  ElMessage.success('简历已创建');
  await router.push({ name: 'ResumeStudio', params: { id: resume.id } });
}

function openStudio(resume: ResumeV2) {
  router.push({ name: 'ResumeStudio', params: { id: resume.id } });
}

async function removeResume(resume: ResumeV2) {
  await ElMessageBox.confirm(`删除“${resume.title}”？不可变版本、分享链接和导出文件也会一并删除。`, '删除简历', {
    type: 'warning',
    confirmButtonText: '删除',
  });
  await deleteResumeV2Api(resume.id);
  resumes.value = resumes.value.filter(item => item.id !== resume.id);
  ElMessage.success('简历已删除');
}

function onFileChange(file: UploadFile) {
  uploadFile.value = file;
  if (!uploadTitle.value) uploadTitle.value = file.name.replace(/\.[^.]+$/, '');
}

async function submitImport() {
  if (!uploadFile.value?.raw) {
    ElMessage.warning('请先选择文件');
    return;
  }
  uploading.value = true;
  try {
    const form = new FormData();
    form.append('file', uploadFile.value.raw);
    if (uploadTitle.value) form.append('title', uploadTitle.value);
    const accepted = await importResumeV2Api(form);
    uploadVisible.value = false;
    ElMessage.success(`导入任务已受理（${accepted.operation_id.slice(0, 8)}）`);
    await load();
  } finally {
    uploading.value = false;
  }
}

function resetUpload() {
  uploadFile.value = null;
  uploadTitle.value = '';
  uploadRef.value?.clearFiles();
}

const statusText = (status: string) => ({
  draft: '编辑中',
  ready: '可投递',
  archived: '已归档',
}[status] || status);

onMounted(load);
</script>

<template>
  <main class="resume-library">
    <section class="hero">
      <div>
        <span class="eyebrow">Resume Intelligence</span>
        <h1>把经历整理成可信、可投递的简历</h1>
        <p>结构化编辑、ATS 检查、岗位定制、证据约束改写、版本 Diff 与稳定导出集中在同一个工作台。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="UploadFilled" @click="uploadVisible = true">导入简历</el-button>
        <el-button type="primary" :icon="DocumentAdd" @click="createResume">创建结构化简历</el-button>
      </div>
    </section>

    <section class="library-panel" v-loading="loading">
      <header>
        <div>
          <h2>简历库</h2>
          <p>{{ resumes.length }} 份简历 · JSON Resume 1.3.1 唯一事实源</p>
        </div>
      </header>

      <el-empty v-if="!loading && !resumes.length" description="还没有简历">
        <el-button type="primary" @click="createResume">创建第一份简历</el-button>
      </el-empty>

      <div v-else class="resume-grid">
        <article v-for="resume in resumes" :key="resume.id" class="resume-card" @click="openStudio(resume)">
          <div class="card-top">
            <span class="status" :data-status="resume.status">{{ statusText(resume.status) }}</span>
            <el-tag v-if="resume.is_default" size="small" effect="plain">默认简历</el-tag>
          </div>
          <div>
            <h3>{{ resume.title }}</h3>
            <p>{{ resume.current_version?.resume_json?.basics?.label || '尚未填写目标职位' }}</p>
          </div>
          <dl>
            <div><dt>内容版本</dt><dd>v{{ resume.current_version?.version_number || 1 }}</dd></div>
            <div><dt>母版</dt><dd>{{ resume.current_design_revision?.template_key || 'ATS Classic' }}</dd></div>
            <div><dt>更新</dt><dd>{{ formatDateTime(resume.updated_at) }}</dd></div>
          </dl>
          <footer>
            <el-button link type="danger" @click.stop="removeResume(resume)">删除</el-button>
            <span>进入 Studio <el-icon><ArrowRight /></el-icon></span>
          </footer>
        </article>
      </div>
    </section>

    <el-dialog v-model="uploadVisible" title="导入现有简历" width="min(520px, 92vw)" @closed="resetUpload">
      <el-form label-position="top">
        <el-form-item label="简历名称">
          <el-input v-model="uploadTitle" placeholder="默认使用文件名" />
        </el-form-item>
        <el-form-item label="文件">
          <el-upload
            ref="uploadRef"
            class="uploader"
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽或点击选择 PDF、DOCX、TXT、Markdown、JSON</div>
            <template #tip><div class="el-upload__tip">最大 15 MB；解析完成后必须人工确认，AI 不会直接改写事实。</div></template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitImport">开始解析</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.resume-library { min-height: calc(100vh - 60px); padding: 28px; color: #172033; background: #f4f6f8; }
.hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; padding: 36px; border-radius: 24px; color: #fff; background: linear-gradient(120deg, #0f172a 0%, #1e3a5f 58%, #0f766e 120%); box-shadow: 0 22px 50px rgba(15, 23, 42, .18); }
.eyebrow { color: #99f6e4; font-size: 12px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
h1 { max-width: 760px; margin: 10px 0 12px; font-size: clamp(30px, 4vw, 46px); line-height: 1.12; }
.hero p { max-width: 760px; margin: 0; color: #dbeafe; line-height: 1.7; }
.hero-actions { display: flex; flex-shrink: 0; gap: 12px; }
.hero-actions :deep(.el-button) { min-height: 44px; border-radius: 12px; }
.library-panel { margin-top: 24px; padding: 28px; border: 1px solid #e1e6ed; border-radius: 24px; background: #fff; }
.library-panel > header { display: flex; justify-content: space-between; margin-bottom: 22px; }
h2 { margin: 0 0 6px; font-size: 22px; }
.library-panel header p { margin: 0; color: #667085; }
.resume-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 18px; }
.resume-card { display: flex; min-height: 270px; flex-direction: column; justify-content: space-between; padding: 22px; border: 1px solid #e3e8ef; border-radius: 18px; background: linear-gradient(180deg, #fff 0%, #f8fafc 100%); cursor: pointer; transition: .2s ease; }
.resume-card:hover { transform: translateY(-3px); border-color: #94a3b8; box-shadow: 0 15px 30px rgba(15, 23, 42, .08); }
.card-top, .resume-card footer { display: flex; align-items: center; justify-content: space-between; }
.status { color: #92400e; font-size: 13px; font-weight: 700; }
.status[data-status="ready"] { color: #047857; }
.status[data-status="archived"] { color: #64748b; }
.resume-card h3 { margin: 22px 0 8px; font-size: 21px; }
.resume-card p { margin: 0; color: #667085; }
dl { display: grid; gap: 8px; margin: 20px 0; }
dl div { display: flex; justify-content: space-between; gap: 20px; font-size: 13px; }
dt { color: #667085; }
dd { margin: 0; color: #344054; text-align: right; }
.resume-card footer { padding-top: 14px; border-top: 1px solid #e5e7eb; color: #0f766e; font-size: 13px; font-weight: 700; }
.resume-card footer span { display: inline-flex; align-items: center; gap: 4px; }
.uploader { width: 100%; }
.uploader :deep(.el-upload), .uploader :deep(.el-upload-dragger) { width: 100%; }
@media (max-width: 760px) {
  .resume-library { padding: 14px; }
  .hero { align-items: stretch; flex-direction: column; padding: 24px; }
  .hero-actions { display: grid; grid-template-columns: 1fr; }
  .library-panel { padding: 18px; }
}
</style>
