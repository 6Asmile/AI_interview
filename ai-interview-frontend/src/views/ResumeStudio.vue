<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Check, Download, Plus, Refresh, Share } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  acceptResumeSuggestionApi,
  commitResumeDraftApi,
  createResumeShareLinkApi,
  deleteResumeAvatarApi,
  getResumeArtifactApi,
  getResumeAvatarApi,
  getAsyncOperationApi,
  getResumeDraftApi,
  getResumeQualityReportsApi,
  getResumeShareLinksApi,
  getResumeSuggestionsV2Api,
  getResumeTemplatesApi,
  getResumeV2Api,
  getResumeVersionDiffApi,
  getResumeVersionsV2Api,
  patchResumeDraftApi,
  requestResumeExportApi,
  requestResumePreviewApi,
  requestResumeQualityApi,
  requestResumeSuggestionApi,
  rejectResumeSuggestionApi,
  revokeResumeShareLinkApi,
  uploadResumeAvatarApi,
  type JsonResume,
  type ResumeArtifact,
  type ResumeDesign,
  type ResumeDraft,
  type ResumeQualityReport,
  type ResumeShareLink,
  type ResumeSuggestionV2,
  type ResumeTemplate,
  type ResumeV2,
  type ResumeVersionV2,
} from '@/api/modules/resume';
import { formatDateTime } from '@/utils/format';

const route = useRoute();
const router = useRouter();
const resumeId = Number(route.params.id);
const loading = ref(true);
const saving = ref(false);
const saveState = ref<'saved' | 'saving' | 'conflict' | 'error'>('saved');
const activeTab = ref('content');
const resume = ref<ResumeV2 | null>(null);
const draft = ref<ResumeDraft | null>(null);
const content = ref<JsonResume | null>(null);
const design = ref<ResumeDesign | null>(null);
const templates = ref<ResumeTemplate[]>([]);
const versions = ref<ResumeVersionV2[]>([]);
const qualityReports = ref<ResumeQualityReport[]>([]);
const shares = ref<ResumeShareLink[]>([]);
const suggestions = ref<ResumeSuggestionV2[]>([]);
const intelligenceLoading = ref(false);
const intelligenceResult = ref<Record<string, any> | null>(null);
const avatarUrl = ref('');
const avatarUploading = ref(false);
const intelligenceForm = ref({
  task_key: 'resume.rewrite_section',
  instruction: '',
  job_target_id: null as number | null,
});
const previewArtifact = ref<ResumeArtifact | null>(null);
const previewLoading = ref(false);
const qualityLoading = ref(false);
const diffVisible = ref(false);
const diffData = ref<any>(null);
const shareVisible = ref(false);
const shareResult = ref<ResumeShareLink | null>(null);
const shareForm = ref({
  password: '',
  expires_at: '',
  allow_download: false,
  download_limit: null as number | null,
  field_policy: { email: false, phone: false, address: false, image: false },
});
let saveTimer: number | undefined;
let hydrating = true;

const basics = computed(() => content.value?.basics || {});
const latestQuality = computed(() => qualityReports.value.find(item => item.status === 'completed'));
const saveStateText = computed(() => ({
  saved: '草稿已保存',
  saving: '正在保存',
  conflict: '检测到版本冲突',
  error: '保存失败',
}[saveState.value]));

function ensureItemId(item: Record<string, any>) {
  item['x-ifaceoff'] ||= {};
  item['x-ifaceoff'].id ||= crypto.randomUUID();
  return item;
}

function addItem(section: keyof JsonResume) {
  if (!content.value || !Array.isArray(content.value[section])) return;
  const defaults: Record<string, any> = {
    work: { name: '', position: '', startDate: '', endDate: '', summary: '', highlights: [] },
    projects: { name: '', description: '', startDate: '', endDate: '', keywords: [], highlights: [] },
    education: { institution: '', area: '', studyType: '', startDate: '', endDate: '', courses: [] },
    skills: { name: '', level: '', keywords: [] },
  };
  (content.value[section] as Array<Record<string, any>>).push(ensureItemId(defaults[String(section)] || {}));
}

function removeItem(section: keyof JsonResume, index: number) {
  if (content.value && Array.isArray(content.value[section])) {
    (content.value[section] as any[]).splice(index, 1);
  }
}

async function loadAll() {
  loading.value = true;
  try {
    const [resumeData, draftData, templateData, versionData, reportData, shareData, suggestionData, avatarData] = await Promise.all([
      getResumeV2Api(resumeId),
      getResumeDraftApi(resumeId),
      getResumeTemplatesApi(),
      getResumeVersionsV2Api(resumeId),
      getResumeQualityReportsApi(resumeId),
      getResumeShareLinksApi(resumeId),
      getResumeSuggestionsV2Api(resumeId),
      getResumeAvatarApi(resumeId),
    ]);
    resume.value = resumeData;
    draft.value = draftData;
    content.value = structuredClone(draftData.resume_json);
    content.value.basics.location ||= {};
    content.value.basics.profiles ||= [];
    design.value = structuredClone(draftData.design_json);
    templates.value = templateData.templates;
    versions.value = versionData;
    qualityReports.value = reportData;
    shares.value = shareData;
    suggestions.value = suggestionData;
    avatarUrl.value = avatarData.avatar?.url || '';
    await nextTick();
    hydrating = false;
  } finally {
    loading.value = false;
  }
}

async function persistBeforeAssetChange() {
  if (saveTimer) {
    window.clearTimeout(saveTimer);
    saveTimer = undefined;
  }
  await saveDraft();
}

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !draft.value) return;
  avatarUploading.value = true;
  try {
    await persistBeforeAssetChange();
    const result = await uploadResumeAvatarApi(resumeId, draft.value.etag, file);
    const refreshed = await getResumeDraftApi(resumeId);
    draft.value = refreshed;
    content.value = structuredClone(refreshed.resume_json);
    avatarUrl.value = result.avatar.url;
    if (design.value) design.value.show_avatar = true;
    ElMessage.success('头像已安全处理并保存到草稿');
  } finally {
    avatarUploading.value = false;
    input.value = '';
  }
}

async function removeAvatar() {
  if (!draft.value) return;
  await persistBeforeAssetChange();
  const result = await deleteResumeAvatarApi(resumeId, draft.value.etag);
  const refreshed = await getResumeDraftApi(resumeId);
  draft.value = refreshed;
  content.value = structuredClone(refreshed.resume_json);
  avatarUrl.value = '';
  if (design.value) design.value.show_avatar = false;
  ElMessage.success('头像已从后续版本中移除');
  return result;
}

async function saveDraft() {
  if (!draft.value || !content.value || !design.value || saving.value || hydrating) return;
  saving.value = true;
  saveState.value = 'saving';
  try {
    const updated = await patchResumeDraftApi(resumeId, draft.value.etag, {
      resume_json: content.value,
      design_json: design.value,
    });
    draft.value = updated;
    saveState.value = 'saved';
  } catch (error: any) {
    if (error?.response?.status === 409) {
      saveState.value = 'conflict';
      ElMessage.error('草稿已在其他页面修改，请刷新后再继续。');
    } else {
      saveState.value = 'error';
    }
    throw error;
  } finally {
    saving.value = false;
  }
}

function scheduleSave() {
  if (hydrating || saveState.value === 'conflict') return;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => saveDraft().catch(() => undefined), 900);
}

watch(content, scheduleSave, { deep: true });
watch(design, scheduleSave, { deep: true });

async function commitVersion() {
  await saveDraft();
  if (!draft.value) return;
  const summary = await ElMessageBox.prompt('说明本次版本的主要变化，便于后续 Diff 与审计。', '创建不可变版本', {
    inputPlaceholder: '例如：补充项目成果并调整技能顺序',
    inputPattern: /\S+/,
    inputErrorMessage: '请填写变更说明',
  }).then(result => result.value).catch(() => '');
  if (!summary) return;
  await commitResumeDraftApi(resumeId, draft.value.etag, summary);
  draft.value = await getResumeDraftApi(resumeId);
  versions.value = await getResumeVersionsV2Api(resumeId);
  resume.value = await getResumeV2Api(resumeId);
  ElMessage.success('新版本已创建');
}

async function waitForArtifact(id: string) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const artifact = await getResumeArtifactApi(id);
    if (artifact.status === 'ready' || artifact.status === 'failed') return artifact;
    await new Promise(resolve => window.setTimeout(resolve, 750));
  }
  throw new Error('artifact_timeout');
}

async function generatePreview() {
  previewLoading.value = true;
  try {
    await saveDraft();
    const accepted = await requestResumePreviewApi(resumeId);
    if (!accepted.artifact_id) throw new Error('artifact_missing');
    previewArtifact.value = await waitForArtifact(accepted.artifact_id);
    if (previewArtifact.value.status === 'failed') {
      ElMessage.error(previewArtifact.value.error_message || '预览生成失败');
    }
  } catch (error: any) {
    if (error?.message === 'artifact_timeout') ElMessage.warning('预览仍在生成，可稍后刷新。');
  } finally {
    previewLoading.value = false;
  }
}

async function exportResume(format: 'pdf' | 'docx' | 'json') {
  const accepted = await requestResumeExportApi(resumeId, format);
  ElMessage.success(`${format.toUpperCase()} 导出已受理`);
  if (!accepted.artifact_id) return;
  const artifact = await waitForArtifact(accepted.artifact_id).catch(() => null);
  if (artifact?.file_url) window.open(artifact.file_url, '_blank', 'noopener');
  else if (artifact?.status === 'failed') ElMessage.error(artifact.error_message || '导出失败');
}

async function runQualityReview() {
  qualityLoading.value = true;
  try {
    await requestResumeQualityApi(resumeId);
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 650));
      qualityReports.value = await getResumeQualityReportsApi(resumeId);
      if (qualityReports.value.some(item => item.status === 'completed' || item.status === 'failed')) break;
    }
    activeTab.value = 'quality';
  } finally {
    qualityLoading.value = false;
  }
}

async function runIntelligence() {
  intelligenceLoading.value = true;
  intelligenceResult.value = null;
  try {
    await saveDraft();
    const accepted = await requestResumeSuggestionApi(resumeId, intelligenceForm.value);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 750));
      const operation = await getAsyncOperationApi(accepted.operation_id);
      if (['succeeded', 'failed'].includes(operation.status)) {
        intelligenceResult.value = operation;
        break;
      }
    }
    suggestions.value = await getResumeSuggestionsV2Api(resumeId);
    if (intelligenceResult.value?.status === 'failed') {
      ElMessage.error(intelligenceResult.value.error_message || '建议生成失败');
    } else {
      ElMessage.success('证据约束建议已生成');
    }
  } finally {
    intelligenceLoading.value = false;
  }
}

async function acceptSuggestion(suggestion: ResumeSuggestionV2) {
  await ElMessageBox.confirm('采纳后会创建一个新的不可变版本，不会覆盖历史版本。', '采纳建议');
  await acceptResumeSuggestionApi(resumeId, suggestion.id);
  [draft.value, versions.value, suggestions.value, resume.value] = await Promise.all([
    getResumeDraftApi(resumeId),
    getResumeVersionsV2Api(resumeId),
    getResumeSuggestionsV2Api(resumeId),
    getResumeV2Api(resumeId),
  ]);
  content.value = structuredClone(draft.value.resume_json);
  design.value = structuredClone(draft.value.design_json);
  ElMessage.success('建议已采纳并创建新版本');
}

async function rejectSuggestion(suggestion: ResumeSuggestionV2) {
  await rejectResumeSuggestionApi(resumeId, suggestion.id);
  suggestions.value = await getResumeSuggestionsV2Api(resumeId);
}

async function showDiff(version: ResumeVersionV2) {
  diffData.value = await getResumeVersionDiffApi(resumeId, version.id);
  diffVisible.value = true;
}

async function createShare() {
  const payload: Record<string, any> = {
    password: shareForm.value.password,
    allow_download: shareForm.value.allow_download,
    download_limit: shareForm.value.allow_download ? shareForm.value.download_limit : null,
    field_policy: shareForm.value.field_policy,
  };
  if (shareForm.value.expires_at) payload.expires_at = new Date(shareForm.value.expires_at).toISOString();
  shareResult.value = await createResumeShareLinkApi(resumeId, payload);
  shares.value = await getResumeShareLinksApi(resumeId);
  ElMessage.success('私密分享链接已创建，请立即复制令牌');
}

async function copyShare() {
  if (!shareResult.value?.token) return;
  const url = `${window.location.origin}/resume-shares/${shareResult.value.token}`;
  await navigator.clipboard.writeText(url);
  ElMessage.success('分享链接已复制');
}

async function revokeShare(link: ResumeShareLink) {
  await revokeResumeShareLinkApi(resumeId, link.id);
  shares.value = await getResumeShareLinksApi(resumeId);
  ElMessage.success('分享链接已撤销');
}

onMounted(loadAll);
onBeforeUnmount(() => window.clearTimeout(saveTimer));
</script>

<template>
  <main class="studio" v-loading="loading">
    <header class="studio-header">
      <div class="title-row">
        <el-button text :icon="ArrowLeft" @click="router.push('/dashboard/resumes')">简历库</el-button>
        <div>
          <h1>{{ resume?.title || 'Resume Studio' }}</h1>
          <span :class="['save-state', saveState]"><el-icon v-if="saveState === 'saved'"><Check /></el-icon>{{ saveStateText }}</span>
        </div>
      </div>
      <div class="header-actions">
        <el-dropdown @command="exportResume">
          <el-button :icon="Download">导出<el-icon class="el-icon--right"><Download /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="pdf">PDF（同源排版）</el-dropdown-item>
              <el-dropdown-item command="docx">DOCX（ATS 样式）</el-dropdown-item>
              <el-dropdown-item command="json">JSON Resume</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button :loading="qualityLoading" @click="runQualityReview">ATS 检查</el-button>
        <el-button type="primary" @click="commitVersion">创建版本</el-button>
      </div>
    </header>

    <div v-if="content && design" class="studio-body">
      <section class="editor-panel">
        <el-tabs v-model="activeTab" stretch>
          <el-tab-pane label="内容" name="content">
            <div class="pane">
              <section class="form-section">
                <div class="section-heading"><div><span>01</span><h2>基本信息</h2></div></div>
                <el-form label-position="top" class="form-grid">
                  <el-form-item label="姓名"><el-input v-model="basics.name" maxlength="300" /></el-form-item>
                  <el-form-item label="目标职位"><el-input v-model="basics.label" maxlength="300" /></el-form-item>
                  <el-form-item label="邮箱"><el-input v-model="basics.email" type="email" /></el-form-item>
                  <el-form-item label="电话"><el-input v-model="basics.phone" /></el-form-item>
                  <el-form-item label="城市"><el-input v-model="basics.location.city" /></el-form-item>
                  <el-form-item label="个人网站"><el-input v-model="basics.url" placeholder="https://" /></el-form-item>
                  <el-form-item label="职业摘要" class="wide"><el-input v-model="basics.summary" type="textarea" :rows="5" maxlength="20000" show-word-limit /></el-form-item>
                </el-form>
              </section>

              <section class="form-section">
                <div class="section-heading"><div><span>02</span><h2>工作经历</h2></div><el-button :icon="Plus" @click="addItem('work')">添加</el-button></div>
                <article v-for="(item, index) in content.work" :key="item['x-ifaceoff']?.id" class="entry-card">
                  <el-form label-position="top" class="form-grid">
                    <el-form-item label="公司"><el-input v-model="item.name" /></el-form-item>
                    <el-form-item label="职位"><el-input v-model="item.position" /></el-form-item>
                    <el-form-item label="开始日期"><el-input v-model="item.startDate" placeholder="YYYY-MM" /></el-form-item>
                    <el-form-item label="结束日期"><el-input v-model="item.endDate" placeholder="留空表示至今" /></el-form-item>
                    <el-form-item label="职责与成果" class="wide"><el-input v-model="item.summary" type="textarea" :rows="4" /></el-form-item>
                  </el-form>
                  <el-button link type="danger" @click="removeItem('work', index)">删除经历</el-button>
                </article>
              </section>

              <section class="form-section">
                <div class="section-heading"><div><span>03</span><h2>项目经历</h2></div><el-button :icon="Plus" @click="addItem('projects')">添加</el-button></div>
                <article v-for="(item, index) in content.projects" :key="item['x-ifaceoff']?.id" class="entry-card">
                  <el-form label-position="top" class="form-grid">
                    <el-form-item label="项目名称"><el-input v-model="item.name" /></el-form-item>
                    <el-form-item label="技术关键词（逗号分隔）"><el-input :model-value="(item.keywords || []).join(', ')" @update:model-value="item.keywords = String($event).split(',').map(v => v.trim()).filter(Boolean)" /></el-form-item>
                    <el-form-item label="开始日期"><el-input v-model="item.startDate" placeholder="YYYY-MM" /></el-form-item>
                    <el-form-item label="结束日期"><el-input v-model="item.endDate" /></el-form-item>
                    <el-form-item label="项目说明" class="wide"><el-input v-model="item.description" type="textarea" :rows="4" /></el-form-item>
                  </el-form>
                  <el-button link type="danger" @click="removeItem('projects', index)">删除项目</el-button>
                </article>
              </section>

              <section class="form-section">
                <div class="section-heading"><div><span>04</span><h2>教育经历</h2></div><el-button :icon="Plus" @click="addItem('education')">添加</el-button></div>
                <article v-for="(item, index) in content.education" :key="item['x-ifaceoff']?.id" class="entry-card">
                  <el-form label-position="top" class="form-grid">
                    <el-form-item label="学校"><el-input v-model="item.institution" /></el-form-item>
                    <el-form-item label="专业"><el-input v-model="item.area" /></el-form-item>
                    <el-form-item label="学历/学位"><el-input v-model="item.studyType" /></el-form-item>
                    <el-form-item label="时间"><el-input v-model="item.startDate" placeholder="YYYY-MM" /></el-form-item>
                  </el-form>
                  <el-button link type="danger" @click="removeItem('education', index)">删除教育经历</el-button>
                </article>
              </section>

              <section class="form-section">
                <div class="section-heading"><div><span>05</span><h2>专业技能</h2></div><el-button :icon="Plus" @click="addItem('skills')">添加</el-button></div>
                <article v-for="(item, index) in content.skills" :key="item['x-ifaceoff']?.id" class="entry-card compact">
                  <el-form label-position="top" class="form-grid">
                    <el-form-item label="技能分类"><el-input v-model="item.name" placeholder="例如：后端开发" /></el-form-item>
                    <el-form-item label="技能关键词（逗号分隔）"><el-input :model-value="(item.keywords || []).join(', ')" @update:model-value="item.keywords = String($event).split(',').map(v => v.trim()).filter(Boolean)" /></el-form-item>
                  </el-form>
                  <el-button link type="danger" @click="removeItem('skills', index)">删除技能</el-button>
                </article>
              </section>
            </div>
          </el-tab-pane>

          <el-tab-pane label="设计" name="design">
            <div class="pane">
              <div class="template-grid">
                <button v-for="template in templates" :key="template.key" :class="{ active: design.template_key === template.key }" @click="design.template_key = template.key">
                  <strong>{{ template.name[design.language] || template.name['zh-CN'] }}</strong>
                  <span>{{ template.description }}</span>
                </button>
              </div>
              <el-form label-position="top" class="design-form">
                <el-form-item label="语言"><el-segmented v-model="design.language" :options="[{ label: '中文', value: 'zh-CN' }, { label: 'English', value: 'en-US' }]" /></el-form-item>
                <el-form-item label="页面"><el-segmented v-model="design.page_size" :options="['A4', 'Letter']" /></el-form-item>
                <el-form-item label="字体"><el-select v-model="design.font"><el-option v-for="font in ['Noto Sans CJK SC','Noto Serif CJK SC','Source Sans 3','Inter']" :key="font" :value="font" /></el-select></el-form-item>
                <el-form-item label="紧凑度"><el-segmented v-model="design.density" :options="[{ label: '紧凑', value: 'compact' }, { label: '均衡', value: 'balanced' }, { label: '舒展', value: 'comfortable' }]" /></el-form-item>
                <el-form-item label="强调色"><el-color-picker v-model="design.color" /></el-form-item>
                <el-form-item label="头像">
                  <div class="avatar-control">
                    <img v-if="avatarUrl" :src="avatarUrl" alt="简历头像" />
                    <div class="avatar-actions">
                      <el-switch
                        v-model="design.show_avatar"
                        :disabled="!avatarUrl"
                        active-text="显示"
                        inactive-text="隐藏"
                      />
                      <label class="avatar-upload" :class="{ disabled: avatarUploading }">
                        {{ avatarUploading ? '处理中…' : (avatarUrl ? '更换头像' : '上传头像') }}
                        <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="avatarUploading" @change="uploadAvatar" />
                      </label>
                      <el-button v-if="avatarUrl" link type="danger" :disabled="avatarUploading" @click="removeAvatar">移除</el-button>
                    </div>
                  </div>
                </el-form-item>
              </el-form>
              <el-alert title="Studio 仅开放安全参数，不接受任意 CSS、自由画布或用户 Typst。" type="info" :closable="false" />
            </div>
          </el-tab-pane>

          <el-tab-pane label="质量" name="quality">
            <div class="pane quality-pane">
              <div v-if="latestQuality" class="score-card">
                <div><strong>{{ latestQuality.score }}</strong><span>综合质量分</span></div>
                <p>Schema、ATS、内容一致性与证据约束的统一结果。</p>
              </div>
              <el-empty v-else description="创建版本后运行 ATS 检查" />
              <div v-if="latestQuality?.report_json?.consensus?.length" class="issue-list">
                <article v-for="issue in latestQuality.report_json.consensus" :key="`${issue.code}-${issue.pointer}`" :data-priority="issue.priority">
                  <div><strong>{{ issue.message }}</strong><code>{{ issue.pointer || '/' }}</code></div>
                  <el-tag size="small" effect="plain">{{ issue.priority }}</el-tag>
                </article>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="AI 建议" name="intelligence">
            <div class="pane intelligence-pane">
              <el-alert title="AI 只生成 JSON Patch 候选建议；没有已确认 CareerFact 的经历、技能与数字不会被写入。" type="info" :closable="false" />
              <el-form label-position="top" class="intelligence-form">
                <el-form-item label="任务">
                  <el-select v-model="intelligenceForm.task_key">
                    <el-option label="基于职业事实生成" value="resume.from_career_facts" />
                    <el-option label="改写指定栏目" value="resume.rewrite_section" />
                    <el-option label="成果追问教练" value="resume.achievement_coach" />
                    <el-option label="多视角质量复核" value="resume.quality_review" />
                    <el-option label="岗位定制建议" value="resume.jd_tailor" />
                  </el-select>
                </el-form-item>
                <el-form-item v-if="intelligenceForm.task_key === 'resume.jd_tailor'" label="目标岗位 ID">
                  <el-input-number v-model="intelligenceForm.job_target_id" :min="1" />
                </el-form-item>
                <el-form-item label="你的目标（作为不可信数据隔离）">
                  <el-input v-model="intelligenceForm.instruction" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="例如：压缩工作经历，突出分布式系统经验" />
                </el-form-item>
                <el-button type="primary" :loading="intelligenceLoading" @click="runIntelligence">生成候选建议</el-button>
              </el-form>
              <div v-if="intelligenceResult?.metadata?.questions?.length" class="coach-questions">
                <h3>需要你补充确认</h3>
                <ol><li v-for="question in intelligenceResult.metadata.questions" :key="question">{{ question }}</li></ol>
              </div>
              <article v-for="suggestion in suggestions" :key="suggestion.id" class="suggestion-card">
                <div>
                  <div><strong>{{ suggestion.summary }}</strong><el-tag size="small">{{ suggestion.status }}</el-tag></div>
                  <p>{{ suggestion.rationale || '建议已通过输出契约与证据约束校验。' }}</p>
                  <small>Patch {{ suggestion.patch.length }} 条 · 事实证据 {{ suggestion.evidence_links.length }} 条 · 基于版本 #{{ suggestion.base_version }}</small>
                </div>
                <div v-if="suggestion.status === 'pending'">
                  <el-button @click="rejectSuggestion(suggestion)">拒绝</el-button>
                  <el-button type="primary" @click="acceptSuggestion(suggestion)">采纳并创建版本</el-button>
                </div>
              </article>
            </div>
          </el-tab-pane>

          <el-tab-pane label="版本" name="versions">
            <div class="pane">
              <el-timeline>
                <el-timeline-item v-for="version in versions" :key="version.id" :timestamp="formatDateTime(version.created_at)" placement="top">
                  <article class="version-card">
                    <div><strong>v{{ version.version_number }}</strong><el-tag v-if="resume?.current_version?.id === version.id" size="small" type="success">当前</el-tag></div>
                    <p>{{ version.change_summary || '未填写变更说明' }}</p>
                    <small>{{ version.source }} · {{ version.content_hash.slice(0, 12) }} · 证据 {{ version.evidence_links.length }}</small>
                    <el-button link @click="showDiff(version)">查看 Diff</el-button>
                  </article>
                </el-timeline-item>
              </el-timeline>
            </div>
          </el-tab-pane>

          <el-tab-pane label="分享" name="share">
            <div class="pane">
              <el-alert title="默认隐藏邮箱、手机号、精确地址和头像。只有你显式开启的字段才会公开。" type="warning" :closable="false" />
              <el-button type="primary" :icon="Share" class="share-button" @click="shareVisible = true">创建私密分享</el-button>
              <el-table :data="shares">
                <el-table-column prop="token_hint" label="令牌尾号" />
                <el-table-column prop="expires_at" label="过期时间"><template #default="{ row }">{{ row.expires_at ? formatDateTime(row.expires_at) : '永不过期' }}</template></el-table-column>
                <el-table-column prop="download_count" label="下载" width="90" />
                <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_revoked ? 'danger' : 'success'">{{ row.is_revoked ? '已撤销' : '有效' }}</el-tag></template></el-table-column>
                <el-table-column label="操作" width="90"><template #default="{ row }"><el-button v-if="!row.is_revoked" link type="danger" @click="revokeShare(row)">撤销</el-button></template></el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <aside class="preview-panel">
        <header><div><strong>服务端权威预览</strong><small>{{ design.page_size }} · {{ design.language }}</small></div><el-button circle :icon="Refresh" :loading="previewLoading" @click="generatePreview" /></header>
        <div class="preview-stage">
          <img v-if="previewArtifact?.file_url" :src="previewArtifact.file_url" alt="简历服务端预览" />
          <div v-else class="preview-placeholder">
            <span>PDF 与预览使用同一个 RenderCV/Typst 渲染源</span>
            <el-button type="primary" plain :loading="previewLoading" @click="generatePreview">生成预览</el-button>
          </div>
        </div>
        <footer>RenderCV {{ previewArtifact?.renderer_version || '2.8' }} · 可选择文本 · 字体嵌入</footer>
      </aside>
    </div>

    <el-drawer v-model="diffVisible" title="版本 Diff" size="min(680px, 92vw)">
      <el-empty v-if="!diffData?.changes?.length" description="初始版本没有可比较的变化" />
      <div v-else class="diff-list">
        <article v-for="(change, index) in diffData.changes" :key="index" :data-op="change.op">
          <div><el-tag size="small">{{ change.op }}</el-tag><code>{{ change.path }}</code></div>
          <pre>{{ JSON.stringify(change.after ?? change.before, null, 2) }}</pre>
        </article>
      </div>
    </el-drawer>

    <el-dialog v-model="shareVisible" title="创建私密分享" width="min(560px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="访问密码（可选）"><el-input v-model="shareForm.password" type="password" show-password /></el-form-item>
        <el-form-item label="过期时间（可选）"><el-date-picker v-model="shareForm.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item>
        <el-form-item label="公开字段">
          <el-checkbox v-model="shareForm.field_policy.email">邮箱</el-checkbox>
          <el-checkbox v-model="shareForm.field_policy.phone">手机号</el-checkbox>
          <el-checkbox v-model="shareForm.field_policy.address">精确地址</el-checkbox>
          <el-checkbox v-model="shareForm.field_policy.image">头像</el-checkbox>
        </el-form-item>
        <el-form-item><el-switch v-model="shareForm.allow_download" active-text="允许下载" /></el-form-item>
        <el-form-item v-if="shareForm.allow_download" label="最多下载次数"><el-input-number v-model="shareForm.download_limit" :min="1" /></el-form-item>
      </el-form>
      <el-alert v-if="shareResult?.token" title="令牌只显示一次；服务端仅保存 SHA-256 哈希。" type="success" :closable="false">
        <template #default><el-button type="primary" @click="copyShare">复制分享链接</el-button></template>
      </el-alert>
      <template #footer><el-button @click="shareVisible = false">关闭</el-button><el-button type="primary" @click="createShare">创建链接</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.studio { min-height: calc(100vh - 60px); background: #eef1f4; color: #18212f; }
.studio-header { position: sticky; z-index: 10; top: 0; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 14px 24px; border-bottom: 1px solid #dce1e7; background: rgba(255,255,255,.94); backdrop-filter: blur(14px); }
.title-row, .header-actions { display: flex; align-items: center; gap: 12px; }
.title-row h1 { display: inline; margin: 0 12px 0 0; font-size: 20px; }
.save-state { color: #667085; font-size: 12px; }
.save-state.saved { color: #047857; }
.save-state.conflict, .save-state.error { color: #b42318; }
.studio-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 42vw); min-height: calc(100vh - 120px); }
.editor-panel { min-width: 0; padding: 22px; }
.editor-panel :deep(.el-tabs__header) { margin-bottom: 18px; padding: 0 12px; border: 1px solid #dfe4ea; border-radius: 14px; background: #fff; }
.pane { display: grid; gap: 18px; }
.form-section { padding: 22px; border: 1px solid #dfe4ea; border-radius: 16px; background: #fff; }
.section-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.section-heading > div { display: flex; align-items: center; gap: 10px; }
.section-heading span { display: grid; width: 28px; height: 28px; place-items: center; border-radius: 8px; color: #0f766e; background: #ccfbf1; font-size: 12px; font-weight: 800; }
.section-heading h2 { margin: 0; font-size: 18px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.form-grid .wide { grid-column: 1 / -1; }
.entry-card { position: relative; margin-top: 14px; padding: 18px; border: 1px solid #e2e8f0; border-radius: 14px; background: #f8fafc; }
.entry-card.compact { padding-bottom: 10px; }
.template-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.template-grid button { min-height: 112px; padding: 16px; border: 1px solid #d7dde5; border-radius: 14px; color: #344054; background: #fff; text-align: left; cursor: pointer; }
.template-grid button.active { border-color: #0f766e; box-shadow: 0 0 0 2px rgba(15,118,110,.12); }
.template-grid strong, .template-grid span { display: block; }
.template-grid span { margin-top: 8px; color: #667085; line-height: 1.5; }
.design-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; padding: 22px; border-radius: 16px; background: #fff; }
.avatar-control { display: flex; align-items: center; gap: 14px; }
.avatar-control img { width: 64px; height: 64px; border: 1px solid #d9dfe6; border-radius: 50%; object-fit: cover; }
.avatar-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.avatar-upload { padding: 6px 10px; border: 1px solid #cfd6df; border-radius: 7px; color: #344054; cursor: pointer; }
.avatar-upload.disabled { opacity: .55; cursor: wait; }
.avatar-upload input { display: none; }
.preview-panel { position: sticky; top: 72px; height: calc(100vh - 72px); padding: 22px; border-left: 1px solid #d9dfe6; background: #dfe4e9; }
.preview-panel > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.preview-panel strong, .preview-panel small { display: block; }
.preview-panel small { margin-top: 4px; color: #667085; }
.preview-stage { display: grid; height: calc(100% - 84px); place-items: start center; overflow: auto; border-radius: 10px; background: #cbd2d9; box-shadow: inset 0 1px 5px rgba(15,23,42,.12); }
.preview-stage img { display: block; width: min(100%, 760px); min-height: 100%; background: #fff; box-shadow: 0 10px 30px rgba(15,23,42,.18); }
.preview-placeholder { display: grid; width: min(82%, 520px); min-height: 68vh; place-content: center; gap: 18px; padding: 30px; color: #667085; background: #fff; text-align: center; }
.preview-panel > footer { margin-top: 10px; color: #667085; font-size: 12px; text-align: center; }
.score-card { display: flex; align-items: center; gap: 24px; padding: 24px; border-radius: 16px; color: #fff; background: #0f766e; }
.score-card strong, .score-card span { display: block; }
.score-card strong { font-size: 46px; }
.score-card p { margin: 0; }
.issue-list { display: grid; gap: 10px; }
.issue-list article { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px; border-left: 4px solid #f59e0b; border-radius: 10px; background: #fff; }
.issue-list article[data-priority="high"] { border-color: #dc2626; }
.issue-list code, .issue-list strong { display: block; }
.issue-list code { margin-top: 5px; color: #667085; }
.intelligence-form { padding: 20px; border: 1px solid #dfe4ea; border-radius: 14px; background: #fff; }
.coach-questions { padding: 18px; border-radius: 14px; background: #fffbeb; }
.coach-questions h3 { margin-top: 0; }
.suggestion-card { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px; border: 1px solid #dfe4ea; border-radius: 14px; background: #fff; }
.suggestion-card > div > div { display: flex; align-items: center; gap: 8px; }
.suggestion-card p { margin: 8px 0; color: #475467; }
.suggestion-card small { color: #667085; }
.version-card { padding: 14px; border: 1px solid #e1e6ec; border-radius: 12px; background: #fff; }
.version-card > div { display: flex; gap: 8px; }
.version-card p { margin: 8px 0; }
.version-card small { display: block; color: #667085; }
.share-button { justify-self: start; }
.diff-list { display: grid; gap: 12px; }
.diff-list article { padding: 14px; border: 1px solid #e1e6ec; border-left: 4px solid #64748b; border-radius: 10px; }
.diff-list article[data-op="add"] { border-left-color: #059669; }
.diff-list article[data-op="remove"] { border-left-color: #dc2626; }
.diff-list code { margin-left: 8px; }
.diff-list pre { max-height: 240px; overflow: auto; white-space: pre-wrap; }
@media (max-width: 1040px) {
  .studio-header { align-items: flex-start; flex-direction: column; }
  .header-actions { width: 100%; overflow-x: auto; }
  .studio-body { grid-template-columns: 1fr; }
  .preview-panel { position: relative; top: 0; height: 780px; border-top: 1px solid #d9dfe6; border-left: 0; }
}
@media (max-width: 640px) {
  .studio-header, .editor-panel { padding: 12px; }
  .form-grid, .design-form, .template-grid { grid-template-columns: 1fr; }
  .form-grid .wide { grid-column: auto; }
  .header-actions :deep(.el-button) { flex-shrink: 0; }
}
</style>
