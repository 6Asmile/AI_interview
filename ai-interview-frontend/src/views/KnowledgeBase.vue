<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  ElButton,
  ElDialog,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElPagination,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElUpload,
  ElDescriptions,
  ElDescriptionsItem,
  type FormInstance,
} from 'element-plus';
import { Check, Close, Delete, Edit, Plus, Refresh, Search, UploadFilled, View } from '@element-plus/icons-vue';
import { useAuthStore } from '@/store/modules/auth';
import {
  createKnowledgeDocumentApi,
  debugKnowledgeSearchApi,
  deleteKnowledgeDocumentApi,
  getKnowledgeDocumentsApi,
  getKnowledgeImportBatchesApi,
  importKnowledgeBatchApi,
  previewKnowledgeChunksApi,
  previewStructuredKnowledgeChunksApi,
  reindexKnowledgeDocumentApi,
  reparseKnowledgeDocumentApi,
  approveKnowledgeDocumentApi,
  rejectKnowledgeDocumentApi,
  submitKnowledgeDocumentReviewApi,
  updateKnowledgeDocumentApi,
  type KnowledgeApprovalStatus,
  type KnowledgeChunkPreviewItem,
  type KnowledgeChunkPreviewParent,
  type KnowledgeDifficulty,
  type KnowledgeDocument,
  type KnowledgeDocumentPayload,
  type KnowledgeImportBatch,
  type KnowledgeParseStatus,
  type KnowledgeStatus,
  type KnowledgeVisibility,
} from '@/api/modules/knowledge';

const authStore = useAuthStore();
const loading = ref(false);
const documents = ref<KnowledgeDocument[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const formRef = ref<FormInstance>();
const dialogVisible = ref(false);
const previewVisible = ref(false);
const importVisible = ref(false);
const debugVisible = ref(false);
const rejectVisible = ref(false);
const previewLoading = ref(false);
const importLoading = ref(false);
const debugLoading = ref(false);
const previewChunks = ref<KnowledgeChunkPreviewItem[]>([]);
const previewParents = ref<KnowledgeChunkPreviewParent[]>([]);
const previewStrategy = ref('');
const importBatches = ref<KnowledgeImportBatch[]>([]);
const debugResult = ref<{
  contexts: any[];
  retrieval_trace: Record<string, any>;
  retrieval_explanation?: Record<string, any>;
} | null>(null);
const uploadFiles = ref<any[]>([]);
const editingDocument = ref<KnowledgeDocument | null>(null);
const rejectingDocument = ref<KnowledgeDocument | null>(null);
const rejectReason = ref('');

const filters = reactive({
  search: '',
  visibility: '' as KnowledgeVisibility | '',
  status: '' as KnowledgeStatus | '',
  approval_status: '' as KnowledgeApprovalStatus | '',
  difficulty: '' as KnowledgeDifficulty | '',
  job_position: '',
  ability_tag: '',
});

const form = reactive({
  title: '',
  content: '',
  source_type: 'question_bank',
  visibility: 'private' as KnowledgeVisibility,
  difficulty: 'any' as KnowledgeDifficulty,
  job_positions_text: '',
  ability_tags_text: '',
  auto_index: true,
});

const importForm = reactive({
  visibility: 'private' as KnowledgeVisibility,
  difficulty: 'any' as KnowledgeDifficulty,
  job_positions_text: '',
  ability_tags_text: '',
});

const debugForm = reactive({
  job_position: '',
  current_stage: 'technical_deep_dive',
  pending_topics_text: '',
  follow_up_target: '',
  jd_text: '',
  difficulty: '' as KnowledgeDifficulty | '',
  limit: 4,
});

const isAdmin = computed(() => {
  const role = (authStore.user?.role || '').toLowerCase();
  return ['admin', 'staff', 'superuser'].includes(role);
});

const statusMeta: Record<KnowledgeStatus, { label: string; type: 'info' | 'success' | 'warning' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  indexing: { label: '索引中', type: 'warning' },
  indexed: { label: '已索引', type: 'success' },
  failed: { label: '失败', type: 'danger' },
};

const parseMeta: Record<KnowledgeParseStatus, { label: string; type: 'info' | 'success' | 'warning' | 'danger' }> = {
  pending: { label: '待解析', type: 'info' },
  parsing: { label: '解析中', type: 'warning' },
  parsed: { label: '已解析', type: 'success' },
  failed: { label: '解析失败', type: 'danger' },
};

const approvalMeta: Record<KnowledgeApprovalStatus, { label: string; type: 'info' | 'success' | 'warning' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  pending_review: { label: '待审核', type: 'warning' },
  approved: { label: '已上线', type: 'success' },
  rejected: { label: '已拒绝', type: 'danger' },
  archived: { label: '已归档', type: 'info' },
};

const visibilityMeta: Record<KnowledgeVisibility, { label: string; type: 'info' | 'success' }> = {
  private: { label: '私有', type: 'info' },
  public: { label: '公共', type: 'success' },
};

const difficultyLabel: Record<KnowledgeDifficulty, string> = {
  any: '不限',
  easy: '基础',
  medium: '中等',
  hard: '高阶',
};

const splitList = (text: string) => text.split(',').map(item => item.trim()).filter(Boolean);

const blockTypeLabel: Record<string, string> = {
  paragraph: '段落',
  section: '章节',
  legacy_text: '文本',
  manual: '手动',
  table: '表格',
  faq: 'FAQ',
  ocr: 'OCR',
  page: '页面',
};

const formatTime = (value?: string | null) => {
  if (!value) return '-';
  return new Date(value).toLocaleString();
};

const loadDocuments = async () => {
  loading.value = true;
  try {
    const response = await getKnowledgeDocumentsApi({
      page: page.value,
      page_size: pageSize.value,
      ...filters,
    });
    if (Array.isArray(response)) {
      documents.value = response;
      total.value = response.length;
    } else {
      documents.value = response.results;
      total.value = response.count;
    }
  } finally {
    loading.value = false;
  }
};

const loadImportBatches = async () => {
  const response = await getKnowledgeImportBatchesApi({ page: 1, page_size: 5 });
  importBatches.value = Array.isArray(response) ? response : response.results;
};

const resetForm = () => {
  editingDocument.value = null;
  form.title = '';
  form.content = '';
  form.source_type = 'question_bank';
  form.visibility = 'private';
  form.difficulty = 'any';
  form.job_positions_text = '';
  form.ability_tags_text = '';
  form.auto_index = true;
  previewChunks.value = [];
  previewParents.value = [];
  previewStrategy.value = '';
  formRef.value?.clearValidate();
};

const openCreate = () => {
  resetForm();
  dialogVisible.value = true;
};

const openEdit = (document: KnowledgeDocument) => {
  editingDocument.value = document;
  form.title = document.title;
  form.content = document.content;
  form.source_type = document.source_type || 'question_bank';
  form.visibility = document.visibility;
  form.difficulty = document.difficulty;
  form.job_positions_text = (document.job_positions || []).join(', ');
  form.ability_tags_text = (document.ability_tags || []).join(', ');
  form.auto_index = false;
  previewChunks.value = [];
  previewParents.value = [];
  previewStrategy.value = '';
  dialogVisible.value = true;
};

const buildPayload = (): KnowledgeDocumentPayload => ({
  title: form.title.trim(),
  content: form.content.trim(),
  source_type: form.source_type.trim() || 'question_bank',
  visibility: isAdmin.value ? form.visibility : 'private',
  difficulty: form.difficulty,
  job_positions: splitList(form.job_positions_text),
  ability_tags: splitList(form.ability_tags_text),
  auto_index: form.auto_index,
});

const submitDocument = async () => {
  await formRef.value?.validate();
  const payload = buildPayload();
  if (editingDocument.value) {
    await updateKnowledgeDocumentApi(editingDocument.value.id, payload);
    ElMessage.success('知识库已更新');
  } else {
    await createKnowledgeDocumentApi(payload);
    ElMessage.success('知识库已创建');
  }
  dialogVisible.value = false;
  await loadDocuments();
};

const removeDocument = async (document: KnowledgeDocument) => {
  await ElMessageBox.confirm(`确定删除“${document.title}”？`, '删除知识库', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  });
  await deleteKnowledgeDocumentApi(document.id);
  ElMessage.success('已删除');
  await loadDocuments();
};

const reindexDocument = async (document: KnowledgeDocument) => {
  await reindexKnowledgeDocumentApi(document.id);
  ElMessage.success('索引任务已提交');
  await loadDocuments();
};

const reparseDocument = async (document: KnowledgeDocument) => {
  await reparseKnowledgeDocumentApi(document.id);
  ElMessage.success('解析任务已提交');
  await loadDocuments();
};

const previewCurrentContent = async () => {
  if (!form.content.trim()) {
    ElMessage.warning('请先填写知识库内容');
    return;
  }
  previewLoading.value = true;
  try {
    if (editingDocument.value) {
      const response = await previewStructuredKnowledgeChunksApi(editingDocument.value.id);
      previewParents.value = response.parents || [];
      previewChunks.value = response.chunks || response.parents.flatMap(parent => parent.children);
      previewStrategy.value = response.strategy || '';
    } else {
      const response = await previewKnowledgeChunksApi({ title: form.title || '切块预览', content: form.content });
      previewParents.value = response.parents || [];
      previewChunks.value = response.chunks;
      previewStrategy.value = response.strategy || '';
    }
    previewVisible.value = true;
  } finally {
    previewLoading.value = false;
  }
};

const applyFilters = () => {
  page.value = 1;
  loadDocuments();
};

const resetFilters = () => {
  filters.search = '';
  filters.visibility = '';
  filters.status = '';
  filters.approval_status = '';
  filters.difficulty = '';
  filters.job_position = '';
  filters.ability_tag = '';
  applyFilters();
};

const submitReview = async (document: KnowledgeDocument) => {
  await submitKnowledgeDocumentReviewApi(document.id);
  ElMessage.success('已提交审核');
  await loadDocuments();
};

const approveDocument = async (document: KnowledgeDocument) => {
  await approveKnowledgeDocumentApi(document.id);
  ElMessage.success('已审批通过，索引任务已提交');
  await loadDocuments();
};

const openReject = (document: KnowledgeDocument) => {
  rejectingDocument.value = document;
  rejectReason.value = '';
  rejectVisible.value = true;
};

const rejectDocument = async () => {
  if (!rejectingDocument.value || !rejectReason.value.trim()) {
    ElMessage.warning('请输入拒绝原因');
    return;
  }
  await rejectKnowledgeDocumentApi(rejectingDocument.value.id, rejectReason.value.trim());
  ElMessage.success('已拒绝');
  rejectVisible.value = false;
  await loadDocuments();
};

const openImport = async () => {
  uploadFiles.value = [];
  importForm.visibility = 'private';
  importForm.difficulty = 'any';
  importForm.job_positions_text = '';
  importForm.ability_tags_text = '';
  importVisible.value = true;
  await loadImportBatches();
};

const openDebugSearch = () => {
  debugForm.job_position = filters.job_position || '';
  debugForm.pending_topics_text = filters.ability_tag || '';
  debugForm.difficulty = filters.difficulty || '';
  debugForm.follow_up_target = '';
  debugForm.jd_text = '';
  debugForm.limit = 4;
  debugResult.value = null;
  debugVisible.value = true;
};

const runDebugSearch = async () => {
  if (!debugForm.job_position.trim() && !debugForm.pending_topics_text.trim() && !debugForm.follow_up_target.trim()) {
    ElMessage.warning('请至少填写岗位、能力标签或追问目标');
    return;
  }
  debugLoading.value = true;
  try {
    debugResult.value = await debugKnowledgeSearchApi({
      job_position: debugForm.job_position.trim(),
      current_stage: debugForm.current_stage,
      pending_topics: splitList(debugForm.pending_topics_text),
      last_evaluation: {
        follow_up_target: debugForm.follow_up_target.trim(),
      },
      jd_text: debugForm.jd_text,
      difficulty: debugForm.difficulty,
      limit: debugForm.limit,
    });
  } finally {
    debugLoading.value = false;
  }
};

const submitImport = async () => {
  if (!uploadFiles.value.length) {
    ElMessage.warning('请先选择文件');
    return;
  }
  const data = new FormData();
  uploadFiles.value.forEach(item => {
    const rawFile = item.raw || item;
    data.append('files', rawFile);
  });
  data.append('visibility', isAdmin.value ? importForm.visibility : 'private');
  data.append('difficulty', importForm.difficulty);
  data.append('job_positions', importForm.job_positions_text);
  data.append('ability_tags', importForm.ability_tags_text);
  importLoading.value = true;
  try {
    const batch = await importKnowledgeBatchApi(data);
    ElMessage.success(`导入完成：成功 ${batch.success_count}，失败 ${batch.failed_count}`);
    uploadFiles.value = [];
    await Promise.all([loadDocuments(), loadImportBatches()]);
  } finally {
    importLoading.value = false;
  }
};

onMounted(async () => {
  await Promise.all([loadDocuments(), loadImportBatches()]);
});
</script>

<template>
  <div class="knowledge-page">
    <div class="page-heading">
      <div>
        <h1>知识库</h1>
        <p>管理面试题库、能力点和岗位知识，供 AI 面试官检索使用。</p>
      </div>
      <div class="heading-actions">
        <el-button :icon="Search" @click="openDebugSearch">检索调试</el-button>
        <el-button :icon="UploadFilled" @click="openImport">批量导入</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建知识库</el-button>
      </div>
    </div>

    <section class="toolbar">
      <el-input
        v-model="filters.search"
        class="filter-input"
        clearable
        placeholder="搜索标题或内容"
        :prefix-icon="Search"
        @keyup.enter="applyFilters"
      />
      <el-input v-model="filters.job_position" class="filter-input" clearable placeholder="岗位" />
      <el-input v-model="filters.ability_tag" class="filter-input" clearable placeholder="能力标签" />
      <el-select v-model="filters.visibility" class="filter-select" clearable placeholder="范围">
        <el-option label="私有" value="private" />
        <el-option label="公共" value="public" />
      </el-select>
      <el-select v-model="filters.status" class="filter-select" clearable placeholder="索引状态">
        <el-option label="草稿" value="draft" />
        <el-option label="索引中" value="indexing" />
        <el-option label="已索引" value="indexed" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-select v-model="filters.approval_status" class="filter-select" clearable placeholder="审批状态">
        <el-option label="草稿" value="draft" />
        <el-option label="待审核" value="pending_review" />
        <el-option label="已上线" value="approved" />
        <el-option label="已拒绝" value="rejected" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-select v-model="filters.difficulty" class="filter-select" clearable placeholder="难度">
        <el-option label="不限" value="any" />
        <el-option label="基础" value="easy" />
        <el-option label="中等" value="medium" />
        <el-option label="高阶" value="hard" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="applyFilters">筛选</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </section>

    <section class="table-panel">
      <el-table v-loading="loading" :data="documents" stripe height="calc(100vh - 300px)">
        <el-table-column prop="title" label="标题" min-width="210">
          <template #default="{ row }">
            <div class="title-cell">
              <span>{{ row.title }}</span>
              <small>{{ row.source_type || 'question_bank' }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="范围" width="90">
          <template #default="{ row }">
            <el-tag :type="visibilityMeta[row.visibility as KnowledgeVisibility].type">
              {{ visibilityMeta[row.visibility as KnowledgeVisibility].label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="难度" width="90">
          <template #default="{ row }">{{ difficultyLabel[row.difficulty as KnowledgeDifficulty] }}</template>
        </el-table-column>
        <el-table-column label="岗位 / 能力" min-width="220">
          <template #default="{ row }">
            <div class="tag-line">
              <el-tag v-for="item in row.job_positions" :key="item" size="small">{{ item }}</el-tag>
            </div>
            <div class="tag-line muted">
              <el-tag v-for="item in row.ability_tags" :key="item" size="small" type="info">{{ item }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status as KnowledgeStatus].type">
              {{ statusMeta[row.status as KnowledgeStatus].label }}
            </el-tag>
            <div class="subtext">{{ row.chunk_count }} chunks</div>
          </template>
        </el-table-column>
        <el-table-column label="解析" width="130">
          <template #default="{ row }">
            <el-tag :type="parseMeta[row.parse_status as KnowledgeParseStatus].type">
              {{ parseMeta[row.parse_status as KnowledgeParseStatus].label }}
            </el-tag>
            <div class="subtext">{{ row.parser_name || '-' }}{{ row.ocr_enabled ? ' / OCR' : '' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="审批" width="130">
          <template #default="{ row }">
            <el-tag :type="approvalMeta[row.approval_status as KnowledgeApprovalStatus].type">
              {{ approvalMeta[row.approval_status as KnowledgeApprovalStatus].label }}
            </el-tag>
            <div v-if="row.rejection_reason" class="subtext danger-text">{{ row.rejection_reason }}</div>
          </template>
        </el-table-column>
        <el-table-column label="使用情况" width="180">
          <template #default="{ row }">
            <div>{{ row.retrieval_count }} 次命中</div>
            <div class="subtext">最近：{{ formatTime(row.last_retrieved_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">
            <div>{{ formatTime(row.updated_at) }}</div>
            <div class="subtext">索引：{{ formatTime(row.last_indexed_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button :icon="View" size="small" @click="openEdit(row)">查看</el-button>
            <el-button
              v-if="row.can_submit_review"
              size="small"
              type="primary"
              @click="submitReview(row)"
            >
              提审
            </el-button>
            <el-button
              v-if="row.can_approve"
              :icon="Check"
              size="small"
              type="success"
              @click="approveDocument(row)"
            />
            <el-button
              v-if="row.can_approve"
              :icon="Close"
              size="small"
              type="danger"
              @click="openReject(row)"
            />
            <el-button
              v-if="row.can_edit"
              :icon="Refresh"
              size="small"
              :disabled="row.status === 'indexing' || row.approval_status !== 'approved'"
              @click="reindexDocument(row)"
            />
            <el-button
              v-if="row.can_edit && row.source_file"
              size="small"
              :disabled="row.parse_status === 'parsing'"
              @click="reparseDocument(row)"
            >
              解析
            </el-button>
            <el-button v-if="row.can_edit" :icon="Edit" size="small" @click="openEdit(row)" />
            <el-button v-if="row.can_edit" :icon="Delete" size="small" type="danger" @click="removeDocument(row)" />
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          layout="total, sizes, prev, pager, next"
          :page-sizes="[10, 20, 50]"
          :total="total"
          @size-change="loadDocuments"
          @current-change="loadDocuments"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingDocument ? '知识库详情' : '新建知识库'" width="760px">
      <el-form ref="formRef" :model="form" label-width="88px">
        <el-form-item label="标题" prop="title" :rules="[{ required: true, message: '请输入标题' }]">
          <el-input v-model="form.title" :disabled="!!editingDocument && !editingDocument.can_edit" />
        </el-form-item>
        <el-form-item label="范围">
          <el-select v-model="form.visibility" :disabled="!isAdmin || (!!editingDocument && !editingDocument.can_edit)">
            <el-option label="私有" value="private" />
            <el-option label="公共" value="public" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="form.difficulty" :disabled="!!editingDocument && !editingDocument.can_edit">
            <el-option label="不限" value="any" />
            <el-option label="基础" value="easy" />
            <el-option label="中等" value="medium" />
            <el-option label="高阶" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="岗位">
          <el-input
            v-model="form.job_positions_text"
            :disabled="!!editingDocument && !editingDocument.can_edit"
            placeholder="多个岗位用英文逗号分隔"
          />
        </el-form-item>
        <el-form-item label="能力标签">
          <el-input
            v-model="form.ability_tags_text"
            :disabled="!!editingDocument && !editingDocument.can_edit"
            placeholder="例如 RAG, Agent, MySQL"
          />
        </el-form-item>
        <el-form-item label="内容" prop="content" :rules="[{ required: true, message: '请输入内容' }]">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="12"
            :disabled="!!editingDocument && !editingDocument.can_edit"
            placeholder="粘贴岗位知识、题库条目、追问策略或评分要点"
          />
        </el-form-item>
        <el-form-item v-if="!editingDocument || editingDocument.can_edit" label="保存后">
          <el-switch v-model="form.auto_index" active-text="自动重建索引" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :loading="previewLoading" :icon="View" @click="previewCurrentContent">预览切分</el-button>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button v-if="!editingDocument || editingDocument.can_edit" type="primary" @click="submitDocument">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="previewVisible" title="结构化 Chunk 预览" size="680px">
      <div class="preview-summary">
        <span>{{ previewStrategy || 'hierarchical_recursive_semantic' }}</span>
        <strong>{{ previewParents.length }} 个父块 / {{ previewChunks.length }} 个子块</strong>
      </div>
      <div class="preview-list">
        <div v-for="parent in previewParents" :key="parent.parent_index" class="preview-parent">
          <div class="preview-parent-head">
            <div>
              <strong>#{{ parent.parent_index + 1 }} {{ blockTypeLabel[parent.block_type] || parent.block_type || '文本' }}</strong>
              <span v-if="parent.heading_path?.length">{{ parent.heading_path.join(' / ') }}</span>
            </div>
            <small>{{ parent.child_count }} chunks · {{ parent.token_count || 0 }} tokens</small>
          </div>
          <p class="preview-parent-content">{{ parent.content }}</p>
          <div class="preview-children">
            <div v-for="chunk in parent.children" :key="`${parent.parent_index}-${chunk.child_index}`" class="preview-item">
              <div class="preview-title">
                <span>#{{ chunk.chunk_index + 1 }}</span>
                <span>{{ chunk.token_count || 0 }} tokens · {{ chunk.length }} 字符</span>
              </div>
              <p>{{ chunk.content }}</p>
            </div>
          </div>
        </div>
        <div v-if="!previewParents.length" class="empty-preview">没有可预览的切块。</div>
      </div>
    </el-drawer>

    <el-dialog v-model="importVisible" title="批量导入知识库" width="760px">
      <el-form label-width="88px">
        <el-form-item label="文件">
          <el-upload
            v-model:file-list="uploadFiles"
            drag
            multiple
            :auto-upload="false"
            accept=".md,.txt,.pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.bmp"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽或点击上传 md / txt / pdf / docx / xlsx / csv / 图片</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="范围">
          <el-select v-model="importForm.visibility" :disabled="!isAdmin">
            <el-option label="私有" value="private" />
            <el-option label="公共" value="public" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="importForm.difficulty">
            <el-option label="不限" value="any" />
            <el-option label="基础" value="easy" />
            <el-option label="中等" value="medium" />
            <el-option label="高阶" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="岗位">
          <el-input v-model="importForm.job_positions_text" placeholder="可选；多个岗位用英文逗号分隔" />
        </el-form-item>
        <el-form-item label="能力标签">
          <el-input v-model="importForm.ability_tags_text" placeholder="可选；例如 RAG, Agent, MySQL" />
        </el-form-item>
      </el-form>
      <div class="import-history" v-if="importBatches.length">
        <h3>最近导入</h3>
        <div v-for="batch in importBatches" :key="batch.id" class="import-batch">
          <div>
            <strong>{{ batch.status }}</strong>
            <span>成功 {{ batch.success_count }} / 失败 {{ batch.failed_count }} / 共 {{ batch.total_files }}</span>
          </div>
          <div v-for="item in batch.error_log" :key="item.file" class="subtext danger-text">
            {{ item.file }}：{{ item.error }}
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importLoading" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rejectVisible" title="拒绝知识库" width="460px">
      <el-input
        v-model="rejectReason"
        type="textarea"
        :rows="4"
        placeholder="请输入拒绝原因，便于创建者修改后重新提交"
      />
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" @click="rejectDocument">确认拒绝</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="debugVisible" title="知识库检索调试" size="720px">
      <div class="debug-panel">
        <el-form label-width="96px">
          <el-form-item label="岗位">
            <el-input v-model="debugForm.job_position" placeholder="例如 AI 应用开发" />
          </el-form-item>
          <el-form-item label="阶段">
            <el-select v-model="debugForm.current_stage">
              <el-option label="简历深挖" value="resume_deep_dive" />
              <el-option label="技术深挖" value="technical_deep_dive" />
              <el-option label="行为面试" value="behavioral" />
              <el-option label="收尾" value="wrap_up" />
            </el-select>
          </el-form-item>
          <el-form-item label="能力标签">
            <el-input v-model="debugForm.pending_topics_text" placeholder="多个标签用英文逗号分隔" />
          </el-form-item>
          <el-form-item label="追问目标">
            <el-input v-model="debugForm.follow_up_target" placeholder="例如 追问 RRF 和 Rerank 设计" />
          </el-form-item>
          <el-form-item label="难度">
            <el-select v-model="debugForm.difficulty" clearable>
              <el-option label="不限" value="" />
              <el-option label="基础" value="easy" />
              <el-option label="中等" value="medium" />
              <el-option label="高阶" value="hard" />
            </el-select>
          </el-form-item>
          <el-form-item label="JD 摘要">
            <el-input v-model="debugForm.jd_text" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="TopK">
            <el-input v-model.number="debugForm.limit" type="number" min="1" max="10" />
          </el-form-item>
        </el-form>
        <div class="debug-actions">
          <el-button type="primary" :loading="debugLoading" @click="runDebugSearch">执行检索</el-button>
        </div>

        <div v-if="debugResult" class="debug-result">
          <h3>检索链路</h3>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="Query 数">{{ debugResult.retrieval_trace?.queries?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="向量候选">{{ debugResult.retrieval_trace?.vector_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="关键词候选">{{ debugResult.retrieval_trace?.keyword_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="RRF 候选">{{ debugResult.retrieval_trace?.rrf_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="过滤数量">{{ debugResult.retrieval_trace?.filtered_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="Rerank">{{ debugResult.retrieval_trace?.rerank_used ? '已使用' : '未使用/未改变排序' }}</el-descriptions-item>
            <el-descriptions-item label="可用 Chunk">{{ debugResult.retrieval_explanation?.candidate_summary?.eligible_chunk_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="最终命中">{{ debugResult.retrieval_explanation?.candidate_summary?.final_count || 0 }}</el-descriptions-item>
            <el-descriptions-item v-if="debugResult.retrieval_explanation?.fallback_reason" label="降级原因" :span="2">
              {{ debugResult.retrieval_explanation.fallback_reason }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="debug-step-list" v-if="debugResult.retrieval_explanation?.steps?.length">
            <h4>执行步骤</h4>
            <div
              v-for="step in debugResult.retrieval_explanation.steps"
              :key="step.name"
              class="debug-step"
            >
              <div>
                <strong>{{ step.name }}</strong>
                <span>{{ step.summary }}</span>
              </div>
              <el-tag size="small" :type="step.status === 'ok' ? 'success' : step.status === 'degraded' || step.status === 'failed' ? 'danger' : 'warning'">
                {{ step.status }}
              </el-tag>
            </div>
          </div>

          <div class="debug-filter-list" v-if="Object.keys(debugResult.retrieval_explanation?.filters || {}).length">
            <h4>过滤原因</h4>
            <el-tag
              v-for="(count, reason) in debugResult.retrieval_explanation?.filters"
              :key="reason"
              class="debug-filter-tag"
              type="warning"
            >
              {{ reason }}: {{ count }}
            </el-tag>
          </div>

          <div class="debug-query-list" v-if="debugResult.retrieval_trace?.queries?.length">
            <h4>Multi Query</h4>
            <div v-for="(query, index) in debugResult.retrieval_trace.queries" :key="index" class="debug-query">
              {{ index + 1 }}. {{ query }}
            </div>
          </div>

          <h3>命中片段</h3>
          <div v-if="!debugResult.contexts.length" class="empty-debug">未命中已审批且已索引的知识库。</div>
          <div v-for="context in debugResult.contexts" :key="context.chunk_id" class="debug-context">
            <div class="debug-context-head">
              <strong>{{ context.title }}</strong>
              <span>score {{ context.score ?? '-' }}</span>
            </div>
            <div class="tag-line">
              <el-tag size="small" :type="context.visibility === 'public' ? 'success' : 'info'">{{ context.visibility }}</el-tag>
              <el-tag v-for="tag in context.ability_tags || []" :key="tag" size="small" type="info">{{ tag }}</el-tag>
            </div>
            <p>{{ context.content }}</p>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.knowledge-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.page-heading,
.toolbar,
.table-panel {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
}

.heading-actions {
  display: flex;
  gap: 10px;
}

.page-heading h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 650;
  color: #1f2d3d;
}

.page-heading p {
  margin: 0;
  color: #606266;
  font-size: 14px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px;
}

.filter-input {
  width: 190px;
}

.filter-select {
  width: 130px;
}

.table-panel {
  padding: 12px;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-weight: 600;
}

.title-cell small,
.subtext {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.danger-text {
  color: #f56c6c;
}

.tag-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
}

.tag-line + .tag-line {
  margin-top: 6px;
}

.muted:empty::after {
  content: '-';
  color: #c0c4cc;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.preview-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #f5f7fa;
  color: #606266;
  font-size: 13px;
}

.preview-summary strong {
  color: #303133;
  font-weight: 600;
}

.preview-parent {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

.preview-parent-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.preview-parent-head > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview-parent-head strong {
  color: #303133;
  font-weight: 600;
}

.preview-parent-head span,
.preview-parent-head small {
  color: #909399;
  font-size: 12px;
}

.preview-parent-content {
  display: -webkit-box;
  max-height: 88px;
  margin: 0;
  padding: 10px 12px;
  overflow: hidden;
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.preview-children {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.preview-item {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
}

.preview-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  font-weight: 600;
  color: #303133;
}

.preview-title span:last-child {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.preview-item p {
  margin: 0;
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
}

.empty-preview {
  padding: 24px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  color: #909399;
  text-align: center;
}

.import-history {
  margin-top: 16px;
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.import-history h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.import-batch {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  background: #fafafa;
}

.import-batch > div:first-child {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 4px;
}

.debug-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.debug-actions {
  display: flex;
  justify-content: flex-end;
}

.debug-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}

.debug-result h3,
.debug-result h4 {
  margin: 0;
  color: #303133;
}

.debug-query-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.debug-step-list,
.debug-filter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.debug-step {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafafa;
}

.debug-step > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.debug-step span {
  color: #606266;
  line-height: 1.5;
}

.debug-filter-list {
  flex-direction: row;
  flex-wrap: wrap;
}

.debug-filter-list h4 {
  width: 100%;
}

.debug-filter-tag {
  margin-right: 6px;
}

.debug-query,
.debug-context {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafafa;
}

.debug-query {
  color: #606266;
  line-height: 1.6;
}

.debug-context {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.debug-context-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.debug-context-head span {
  color: #909399;
  font-size: 12px;
}

.debug-context p {
  margin: 0;
  color: #606266;
  line-height: 1.7;
  white-space: pre-wrap;
}

.empty-debug {
  padding: 18px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  color: #909399;
  text-align: center;
}
</style>
