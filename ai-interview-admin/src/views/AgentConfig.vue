<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';

const loading = ref(false);
const activeTab = ref('release');
const profiles = ref<any[]>([]);
const revisions = ref<any[]>([]);
const knowledgeBases = ref<any[]>([]);
const retrievalProfiles = ref<any[]>([]);
const experiments = ref<any[]>([]);
const evaluationDatasets = ref<any[]>([]);
const selectedDatasetId = ref<number | null>(null);
const selectedProfileId = ref('');
const selectedRevisionId = ref('');
const revision = ref<any>(null);
const resolvedPreview = ref<any>(null);
const promptTask = ref('interview.first_question');
const contextText = ref('{}');
const knowledgeBindingsText = ref('[]');
const contextMode = ref('replace');
const knowledgeMode = ref('inherit');
const retrievalDialog = ref(false);
const knowledgeBaseDialog = ref(false);
const retrievalEditor = reactive<any>({
  mode: 'create', revision_id: '', name: '', description: '', config: '{}', operation_reason: '',
});
const knowledgeBaseEditor = reactive<any>({
  mode: 'create', revision_id: '', name: '', description: '',
  default_retrieval_revision_id: '', ingestion_policy: '{}', members: '[]', operation_reason: '',
});
const promptForm = reactive<any>({
  system_template: '', user_template: '', variable_schema: '{}', output_contract: '{}',
  model_alias_id: null, temperature: 0.3, max_output_tokens: 800,
});
const createDialog = ref(false);
const createForm = reactive({
  name: '', description: '', scope: 'template', operation_reason: '',
});
const taskKeys = [
  'interview.first_question',
  'interview.answer_evaluation',
  'interview.next_question',
  'interview.memory_summary',
  'interview.final_report',
  'rag.query_planner',
];

const selectedProfile = computed(() => profiles.value.find(item => item.id === selectedProfileId.value));
const selectedPrompt = computed(() => revision.value?.prompts?.find((item: any) => item.task_key === promptTask.value));
const isDraft = computed(() => revision.value?.status === 'draft');
const canSubmit = computed(() => Boolean(
  revision.value?.validation_report?.valid
  && revision.value?.evaluation_summary?.status === 'succeeded',
));

const loadAll = async () => {
  loading.value = true;
  try {
    const [profileRows, kbRows, retrievalRows, datasetRows] = await Promise.all([
      api.get<any[]>('/agent-config/profiles/'),
      api.get<any[]>('/knowledge-bases/'),
      api.get<any[]>('/retrieval-profiles/'),
      api.get<any[]>('/agent-config/evaluation-datasets/'),
    ]);
    profiles.value = profileRows;
    knowledgeBases.value = kbRows;
    retrievalProfiles.value = retrievalRows;
    evaluationDatasets.value = datasetRows;
    if (!selectedDatasetId.value && datasetRows.length) selectedDatasetId.value = datasetRows[0].id;
    if (!selectedProfileId.value && profiles.value.length) {
      selectedProfileId.value = profiles.value[0].id;
    }
    await loadExperiments();
  } finally {
    loading.value = false;
  }
};

const loadExperiments = async () => {
  try { experiments.value = await api.get('/agent-config/experiments/retrieval/'); }
  catch { experiments.value = []; }
};

const loadRevisions = async () => {
  if (!selectedProfileId.value) return;
  revisions.value = await api.get(`/agent-config/profiles/${selectedProfileId.value}/revisions/`);
  if (!revisions.value.some(item => item.id === selectedRevisionId.value)) {
    selectedRevisionId.value = revisions.value[0]?.id || '';
  } else {
    await loadRevision();
  }
};

const loadRevision = async () => {
  if (!selectedRevisionId.value) {
    revision.value = null;
    return;
  }
  revision.value = await api.get(`/agent-config/revisions/${selectedRevisionId.value}/`);
  contextText.value = JSON.stringify(revision.value.context_policy || {}, null, 2);
  knowledgeBindingsText.value = JSON.stringify(revision.value.knowledge_bindings || [], null, 2);
  contextMode.value = revision.value.context_mode || 'replace';
  knowledgeMode.value = revision.value.knowledge_mode || 'inherit';
  syncPrompt();
  try {
    resolvedPreview.value = await api.get(
      `/agent-config/revisions/${selectedRevisionId.value}/resolved-preview/`,
    );
  } catch {
    resolvedPreview.value = null;
  }
};

const syncPrompt = () => {
  const item = selectedPrompt.value;
  Object.assign(promptForm, {
    system_template: item?.system_template || '',
    user_template: item?.user_template || '',
    variable_schema: JSON.stringify(item?.variable_schema || { required: [] }, null, 2),
    output_contract: JSON.stringify(item?.output_contract || {}, null, 2),
    model_alias_id: item?.model_alias_id || null,
    temperature: item?.temperature ?? 0.3,
    max_output_tokens: item?.max_output_tokens || 800,
  });
};

const askReason = async (title: string) => {
  const result = await ElMessageBox.prompt('操作原因会写入不可篡改审计链。', title, {
    inputPlaceholder: '请输入具体原因',
    inputValidator: value => Boolean(String(value || '').trim()) || '必须填写操作原因',
  });
  return String(result.value).trim();
};

const action = async (name: string) => {
  if (!revision.value) return;
  const reason = await askReason({
    validate: '校验候选版本', evaluate: '运行离线评估', submit: '提交审核',
    approve: '审核通过', publish: '发布版本', rollback: '回滚到该版本',
  }[name] || name);
  await api.post(
    `/agent-config/revisions/${revision.value.id}/${name}/`,
    {
      operation_reason: reason,
      dataset_id: name === 'evaluate' ? selectedDatasetId.value : undefined,
    },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  );
  ElMessage.success('操作已完成并写入审计链。');
  await Promise.all([loadAll(), loadRevisions(), loadRevision()]);
};

const cloneRevision = async () => {
  if (!selectedProfileId.value) return;
  const reason = await askReason('克隆为新草稿');
  const created = await api.post<any>(
    `/agent-config/profiles/${selectedProfileId.value}/revisions/`,
    {
      source_revision_id: selectedRevisionId.value || undefined,
      change_summary: reason,
      operation_reason: reason,
    },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  );
  selectedRevisionId.value = created.id;
  ElMessage.success('新草稿已创建。');
  await loadRevisions();
};

const saveDraft = async () => {
  if (!revision.value || !isDraft.value) return;
  const reason = await askReason('保存 Context 与 Prompt 草稿');
  let contextPolicy: any;
  let variableSchema: any;
  let outputContract: any;
  let knowledgeBindings: any;
  try {
    contextPolicy = JSON.parse(contextText.value);
    variableSchema = JSON.parse(promptForm.variable_schema);
    outputContract = JSON.parse(promptForm.output_contract);
    knowledgeBindings = JSON.parse(knowledgeBindingsText.value);
  } catch {
    ElMessage.error('Context Policy、变量 Schema、输出契约或知识库绑定不是合法 JSON。');
    return;
  }
  const prompts = [...(revision.value.prompts || [])];
  const index = prompts.findIndex((item: any) => item.task_key === promptTask.value);
  const nextPrompt = {
    ...(index >= 0 ? prompts[index] : {}),
    task_key: promptTask.value,
    system_template: promptForm.system_template,
    user_template: promptForm.user_template,
    variable_schema: variableSchema,
    output_contract: outputContract,
    model_alias_id: promptForm.model_alias_id,
    temperature: promptForm.temperature,
    max_output_tokens: promptForm.max_output_tokens,
  };
  if (index >= 0) prompts[index] = nextPrompt;
  else prompts.push(nextPrompt);
  await api.patch(
    `/agent-config/revisions/${revision.value.id}/`,
    {
      operation_reason: reason,
      context_mode: contextMode.value,
      context_policy: contextPolicy,
      prompts,
      knowledge_mode: knowledgeMode.value,
      knowledge_bindings: knowledgeBindings,
    },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  );
  ElMessage.success('草稿已保存；校验和评估结果已失效，请重新运行。');
  await loadRevision();
};

const previewPrompt = async () => {
  if (!revision.value) return;
  const required = JSON.parse(promptForm.variable_schema || '{}').required || [];
  const variables = Object.fromEntries(required.map((key: string) => [key, `[${key} 示例值]`]));
  const result = await api.post<any>(
    `/agent-config/prompts/${promptTask.value}/preview/`,
    { revision_id: revision.value.id, variables },
  );
  await ElMessageBox.alert(
    result.messages.map((item: any) => `${item.role.toUpperCase()}\n${item.content}`).join('\n\n'),
    '严格沙箱渲染预览',
    { customClass: 'prompt-preview-dialog' },
  );
};

const createProfile = async () => {
  const result = await api.post<any>(
    '/agent-config/profiles/',
    createForm,
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  );
  createDialog.value = false;
  selectedProfileId.value = result.profile.id;
  selectedRevisionId.value = result.revision.id;
  ElMessage.success('配置档案与首个草稿已创建。');
  await loadAll();
};

const activeRetrievalRevision = (row: any) => (
  row.revisions?.find((item: any) => item.id === row.active_revision_id) || row.revisions?.[0]
);
const draftRetrievalRevision = (row: any) => row.revisions?.find((item: any) => item.status === 'draft');
const activeKnowledgeRevision = (row: any) => (
  row.revisions?.find((item: any) => item.id === row.active_revision_id) || row.revisions?.[0]
);
const draftKnowledgeRevision = (row: any) => row.revisions?.find((item: any) => item.status === 'draft');

const openRetrievalCreate = () => {
  Object.assign(retrievalEditor, {
    mode: 'create', revision_id: '', name: '', description: '',
    config: JSON.stringify({
      query_count: 5, vector_top_n: 30, keyword_top_n: 30, final_top_k: 4,
      score_threshold: 0.15, rrf_k: 60, vector_weight: 1, keyword_weight: 1,
      rerank_enabled: true, rerank_model_alias: '', parent_expansion: true,
      adjacent_chunks: 1, rag_token_limit: 1800,
    }, null, 2),
    operation_reason: '',
  });
  retrievalDialog.value = true;
};

const openRetrievalDraft = (row: any) => {
  const target = draftRetrievalRevision(row);
  if (!target) return;
  Object.assign(retrievalEditor, {
    mode: 'update', revision_id: target.id, name: row.name, description: row.description,
    config: JSON.stringify(target.config || {}, null, 2), operation_reason: '',
  });
  retrievalDialog.value = true;
};

const saveRetrieval = async () => {
  let config: any;
  try { config = JSON.parse(retrievalEditor.config); }
  catch { ElMessage.error('Retrieval Profile 不是合法 JSON。'); return; }
  const headers = { 'Idempotency-Key': crypto.randomUUID() };
  if (retrievalEditor.mode === 'create') {
    await api.post('/retrieval-profiles/', {
      name: retrievalEditor.name, description: retrievalEditor.description,
      config, operation_reason: retrievalEditor.operation_reason,
    }, { headers });
  } else {
    await api.post(`/retrieval-profiles/revisions/${retrievalEditor.revision_id}/update/`, {
      config, operation_reason: retrievalEditor.operation_reason,
    }, { headers });
  }
  retrievalDialog.value = false;
  ElMessage.success('Retrieval Profile 草稿已保存。');
  await loadAll();
};

const retrievalAction = async (row: any, name: 'clone' | 'publish') => {
  const target = name === 'publish' ? draftRetrievalRevision(row) : activeRetrievalRevision(row);
  if (!target) return;
  const reason = await askReason(name === 'clone' ? '克隆 Retrieval 草稿' : '发布 Retrieval Profile');
  await api.post(`/retrieval-profiles/revisions/${target.id}/${name}/`, {
    operation_reason: reason,
  }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  ElMessage.success('Retrieval Profile 操作已完成。');
  await loadAll();
};

const openKnowledgeBaseCreate = () => {
  const published = retrievalProfiles.value.flatMap(row => row.revisions || [])
    .find((item: any) => item.status === 'published');
  Object.assign(knowledgeBaseEditor, {
    mode: 'create', revision_id: '', name: '', description: '',
    default_retrieval_revision_id: published?.id || '',
    ingestion_policy: JSON.stringify({
      parser: 'docling', ocr_enabled: true, ocr_engine: 'paddleocr',
      ocr_languages: ['ch'], table_structure_enabled: true,
      parent_max_tokens: 1200, child_max_tokens: 420, child_overlap_tokens: 80,
    }, null, 2),
    members: '[]', operation_reason: '',
  });
  knowledgeBaseDialog.value = true;
};

const openKnowledgeBaseDraft = (row: any) => {
  const target = draftKnowledgeRevision(row);
  if (!target) return;
  Object.assign(knowledgeBaseEditor, {
    mode: 'update', revision_id: target.id, name: row.name, description: row.description,
    default_retrieval_revision_id: target.default_retrieval_revision_id,
    ingestion_policy: JSON.stringify(target.ingestion_policy || {}, null, 2),
    members: JSON.stringify((target.members || []).map((item: any) => ({
      document_id: item.document_id, required: item.required, order: item.order,
    })), null, 2),
    operation_reason: '',
  });
  knowledgeBaseDialog.value = true;
};

const saveKnowledgeBase = async () => {
  let ingestionPolicy: any;
  let members: any;
  try {
    ingestionPolicy = JSON.parse(knowledgeBaseEditor.ingestion_policy);
    members = JSON.parse(knowledgeBaseEditor.members);
  } catch {
    ElMessage.error('摄取策略或成员列表不是合法 JSON。');
    return;
  }
  const headers = { 'Idempotency-Key': crypto.randomUUID() };
  if (knowledgeBaseEditor.mode === 'create') {
    const created = await api.post<any>('/knowledge-bases/', {
      name: knowledgeBaseEditor.name, description: knowledgeBaseEditor.description,
      default_retrieval_revision_id: knowledgeBaseEditor.default_retrieval_revision_id,
      ingestion_policy: ingestionPolicy, operation_reason: knowledgeBaseEditor.operation_reason,
    }, { headers });
    if (members.length) {
      await api.patch(`/knowledge-bases/revisions/${created.id}/`, {
        default_retrieval_revision_id: knowledgeBaseEditor.default_retrieval_revision_id,
        ingestion_policy: ingestionPolicy, members,
        operation_reason: knowledgeBaseEditor.operation_reason,
      }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
    }
  } else {
    await api.patch(`/knowledge-bases/revisions/${knowledgeBaseEditor.revision_id}/`, {
      default_retrieval_revision_id: knowledgeBaseEditor.default_retrieval_revision_id,
      ingestion_policy: ingestionPolicy, members,
      operation_reason: knowledgeBaseEditor.operation_reason,
    }, { headers });
  }
  knowledgeBaseDialog.value = false;
  ElMessage.success('知识库草稿已保存。');
  await loadAll();
};

const knowledgeBaseAction = async (row: any, name: 'clone' | 'publish') => {
  const target = name === 'publish' ? draftKnowledgeRevision(row) : activeKnowledgeRevision(row);
  if (!target) return;
  const reason = await askReason(name === 'clone' ? '克隆知识库草稿' : '发布知识库版本');
  await api.post(`/knowledge-bases/revisions/${target.id}/`, {
    action: name, operation_reason: reason,
  }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  ElMessage.success('知识库版本操作已完成。');
  await loadAll();
};

watch(selectedProfileId, loadRevisions);
watch(selectedRevisionId, loadRevision);
watch(promptTask, syncPrompt);
onMounted(loadAll);
</script>

<template>
  <div class="page agent-config" v-loading="loading">
    <header class="page-header">
      <div>
        <h1>Agent 配置中心</h1>
        <p>Context、Prompt、知识库与 RAG 的版本发布、评估、审计和回滚。</p>
      </div>
      <div class="header-actions">
        <el-button @click="createDialog = true">新建配置档案</el-button>
        <el-button type="primary" :disabled="!selectedProfileId" @click="cloneRevision">克隆新草稿</el-button>
      </div>
    </header>

    <section class="selector-band">
      <el-select v-model="selectedProfileId" placeholder="选择平台或模板配置" style="width: 320px">
        <el-option v-for="item in profiles" :key="item.id" :label="`${item.scope === 'platform' ? '平台' : '模板'} · ${item.name}`" :value="item.id" />
      </el-select>
      <el-select v-model="selectedRevisionId" placeholder="选择版本" style="width: 260px">
        <el-option v-for="item in revisions" :key="item.id" :label="`v${item.version} · ${item.status}`" :value="item.id" />
      </el-select>
      <el-tag v-if="revision" :type="revision.status === 'published' ? 'success' : revision.status === 'draft' ? 'info' : 'warning'">
        {{ revision.status }}
      </el-tag>
      <code v-if="revision?.config_hash">{{ revision.config_hash.slice(0, 12) }}</code>
    </section>

    <el-tabs v-model="activeTab" class="config-tabs">
      <el-tab-pane label="发布单" name="release">
        <div class="release-grid" v-if="revision">
          <section class="data-surface release-card">
            <h3>版本状态</h3>
            <dl>
              <div><dt>档案</dt><dd>{{ selectedProfile?.name }}</dd></div>
              <div><dt>版本</dt><dd>v{{ revision.version }}</dd></div>
              <div><dt>基础版本</dt><dd>{{ revision.base_revision_id || '无' }}</dd></div>
              <div><dt>配置哈希</dt><dd class="hash">{{ revision.config_hash || '保存后生成' }}</dd></div>
              <div><dt>最后修改</dt><dd>{{ revision.updated_at }}</dd></div>
            </dl>
          </section>
          <section class="data-surface release-card">
            <h3>发布门禁</h3>
            <el-alert :closable="false" :type="revision.validation_report?.valid ? 'success' : 'warning'" :title="revision.validation_report?.valid ? '硬校验已通过' : '需要运行校验'" />
            <el-alert class="gate" :closable="false" :type="revision.evaluation_summary?.status === 'succeeded' ? 'success' : 'warning'" :title="revision.evaluation_summary?.status === 'succeeded' ? '离线评估已完成' : '需要运行候选版本评估'" />
            <ul v-if="revision.validation_report?.errors?.length">
              <li v-for="error in revision.validation_report.errors" :key="error">{{ error }}</li>
            </ul>
          </section>
        </div>
        <div class="workflow-actions" v-if="revision">
          <el-button v-if="isDraft" @click="action('validate')">校验</el-button>
          <el-select v-if="isDraft" v-model="selectedDatasetId" clearable placeholder="离线评估数据集" style="width: 230px">
            <el-option v-for="item in evaluationDatasets" :key="item.id" :label="`${item.name} · ${item.case_count} cases`" :value="item.id" />
          </el-select>
          <el-button v-if="isDraft" @click="action('evaluate')">离线评估</el-button>
          <el-button v-if="isDraft" type="primary" :disabled="!canSubmit" @click="action('submit')">提交审核</el-button>
          <el-button v-if="revision.status === 'pending_review'" type="primary" @click="action('approve')">审核通过</el-button>
          <el-button v-if="revision.status === 'approved'" type="success" @click="action('publish')">发布</el-button>
          <el-button v-if="['published', 'superseded'].includes(revision.status)" type="warning" @click="action('rollback')">切换/回滚到此版本</el-button>
        </div>
        <div class="data-surface version-table">
          <el-table :data="revisions" highlight-current-row @current-change="(row:any) => row && (selectedRevisionId = row.id)">
            <el-table-column prop="version" label="版本" width="80" />
            <el-table-column prop="status" label="状态" width="130" />
            <el-table-column prop="change_summary" label="变更说明" min-width="220" />
            <el-table-column prop="config_hash" label="配置哈希" min-width="220" show-overflow-tooltip />
            <el-table-column prop="created_at" label="创建时间" min-width="180" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Context" name="context">
        <div class="editor-grid" v-if="revision">
          <section class="editor-panel">
            <div class="panel-title">
              <h3>Context Policy</h3>
              <el-select v-model="contextMode" :disabled="!isDraft" style="width: 150px">
                <el-option label="完整继承" value="inherit" />
                <el-option label="完整替换" value="replace" />
              </el-select>
            </div>
            <el-input v-model="contextText" type="textarea" :rows="25" :readonly="!isDraft" />
          </section>
          <section class="data-surface preview-panel">
            <h3>最终 Envelope 预算预览</h3>
            <div class="token-total">{{ resolvedPreview?.context_preview?.routed_min_context_window || '—' }} <small>最小路由窗口</small></div>
            <el-table :data="Object.entries(resolvedPreview?.context_preview?.section_limits || {}).map(([name, limit]) => ({ name, limit, minimum: resolvedPreview?.context_preview?.section_minimums?.[name] || 0 }))">
              <el-table-column prop="name" label="区域" min-width="170" />
              <el-table-column prop="limit" label="上限 Token" width="120" />
              <el-table-column prop="minimum" label="最小保留" width="110" />
            </el-table>
            <h4>固定裁剪顺序</h4>
            <ol><li v-for="item in resolvedPreview?.context_preview?.drop_order || []" :key="item">{{ item }}</li></ol>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Prompt Registry" name="prompt">
        <div v-if="revision" class="prompt-layout">
          <aside>
            <button v-for="key in taskKeys" :key="key" :class="{ active: promptTask === key }" @click="promptTask = key">{{ key }}</button>
          </aside>
          <section class="editor-panel prompt-editor">
            <div class="panel-title"><h3>{{ promptTask }}</h3><code>{{ selectedPrompt?.content_hash?.slice(0, 12) || '继承/新增' }}</code></div>
            <label>System 模板</label><el-input v-model="promptForm.system_template" type="textarea" :rows="7" :readonly="!isDraft" />
            <label>User 模板</label><el-input v-model="promptForm.user_template" type="textarea" :rows="10" :readonly="!isDraft" />
            <div class="schema-grid">
              <div><label>变量 Schema</label><el-input v-model="promptForm.variable_schema" type="textarea" :rows="7" :readonly="!isDraft" /></div>
              <div><label>输出契约</label><el-input v-model="promptForm.output_contract" type="textarea" :rows="7" :readonly="!isDraft" /></div>
            </div>
            <div class="prompt-controls">
              <el-input-number v-model="promptForm.temperature" :min="0" :max="1" :step="0.1" :disabled="!isDraft" />
              <el-input-number v-model="promptForm.max_output_tokens" :min="64" :max="32768" :disabled="!isDraft" />
              <el-button @click="previewPrompt">渲染预览</el-button>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="知识库 / RAG" name="knowledge">
        <section v-if="revision" class="editor-panel binding-editor">
          <div class="panel-title">
            <div>
              <h3>当前 Agent 版本的知识库绑定</h3>
              <p>支持 inherit / replace；绑定项可指定 knowledge_base_revision_id 与 retrieval_profile_revision_id。</p>
            </div>
            <el-select v-model="knowledgeMode" :disabled="!isDraft" style="width: 150px">
              <el-option label="继承平台知识库" value="inherit" />
              <el-option label="替换知识库绑定" value="replace" />
            </el-select>
          </div>
          <el-input v-model="knowledgeBindingsText" type="textarea" :rows="8" :readonly="!isDraft" />
        </section>
        <div class="two-columns">
          <section class="data-surface">
            <header class="surface-header">
              <div><h3>知识库版本</h3><span>文档成员在会话启动时冻结到发布修订</span></div>
              <el-button size="small" type="primary" @click="openKnowledgeBaseCreate">新建</el-button>
            </header>
            <el-table :data="knowledgeBases">
              <el-table-column prop="name" label="知识库" min-width="180" />
              <el-table-column prop="active_version" label="发布版本" width="100" />
              <el-table-column label="成员" width="90"><template #default="{ row }">{{ row.revisions?.[0]?.members?.length || 0 }}</template></el-table-column>
              <el-table-column label="草稿操作" min-width="220">
                <template #default="{ row }">
                  <el-button v-if="draftKnowledgeRevision(row)" link type="primary" @click="openKnowledgeBaseDraft(row)">编辑</el-button>
                  <el-button v-if="draftKnowledgeRevision(row)" link type="success" @click="knowledgeBaseAction(row, 'publish')">发布</el-button>
                  <el-button v-else-if="activeKnowledgeRevision(row)" link @click="knowledgeBaseAction(row, 'clone')">克隆</el-button>
                </template>
              </el-table-column>
            </el-table>
          </section>
          <section class="data-surface">
            <header class="surface-header">
              <div><h3>Retrieval Profiles</h3><span>多 Query、RRF、Rerank、父块与相邻块展开</span></div>
              <el-button size="small" type="primary" @click="openRetrievalCreate">新建</el-button>
            </header>
            <el-table :data="retrievalProfiles">
              <el-table-column prop="name" label="Profile" min-width="170" />
              <el-table-column prop="active_version" label="发布版本" width="100" />
              <el-table-column label="TopK" width="80"><template #default="{ row }">{{ row.revisions?.[0]?.config?.final_top_k || '—' }}</template></el-table-column>
              <el-table-column label="RAG Token" width="110"><template #default="{ row }">{{ row.revisions?.[0]?.config?.rag_token_limit || '—' }}</template></el-table-column>
              <el-table-column label="草稿操作" min-width="190">
                <template #default="{ row }">
                  <el-button v-if="draftRetrievalRevision(row)" link type="primary" @click="openRetrievalDraft(row)">编辑</el-button>
                  <el-button v-if="draftRetrievalRevision(row)" link type="success" @click="retrievalAction(row, 'publish')">发布</el-button>
                  <el-button v-else-if="activeRetrievalRevision(row)" link @click="retrievalAction(row, 'clone')">克隆</el-button>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="实验评估" name="experiments">
        <div class="data-surface">
          <el-table :data="experiments">
            <el-table-column prop="profile" label="配置档案" min-width="170" />
            <el-table-column prop="evaluation_type" label="类型" width="110" />
            <el-table-column prop="dataset" label="数据集" min-width="150" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column label="硬门禁" width="100"><template #default="{ row }">{{ row.metrics?.hard_gate_pass_rate ?? '—' }}</template></el-table-column>
            <el-table-column label="Retrieval Cases" width="130"><template #default="{ row }">{{ row.metrics?.retrieval_case_count ?? 0 }}</template></el-table-column>
            <el-table-column label="Recall@K" width="100"><template #default="{ row }">{{ row.metrics?.recall_at_k ?? '—' }}</template></el-table-column>
            <el-table-column label="MRR" width="90"><template #default="{ row }">{{ row.metrics?.mrr ?? '—' }}</template></el-table-column>
            <el-table-column label="nDCG" width="90"><template #default="{ row }">{{ row.metrics?.ndcg ?? '—' }}</template></el-table-column>
            <el-table-column label="P95 延迟" width="110"><template #default="{ row }">{{ row.metrics?.p95_latency_ms != null ? `${row.metrics.p95_latency_ms} ms` : '—' }}</template></el-table-column>
            <el-table-column prop="finished_at" label="完成时间" min-width="180" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="revision && isDraft" class="sticky-save">
      <span>修改会使旧校验和评估失效。</span>
      <el-button type="primary" @click="saveDraft">保存当前草稿</el-button>
    </div>

    <el-dialog v-model="createDialog" title="新建 Agent 配置档案" width="520px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="createForm.name" /></el-form-item>
        <el-form-item label="用途"><el-radio-group v-model="createForm.scope"><el-radio-button value="template">模板覆盖</el-radio-button><el-radio-button value="platform">平台默认</el-radio-button></el-radio-group></el-form-item>
        <el-form-item label="说明"><el-input v-model="createForm.description" type="textarea" /></el-form-item>
        <el-form-item label="操作原因"><el-input v-model="createForm.operation_reason" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createDialog = false">取消</el-button><el-button type="primary" :disabled="!createForm.name.trim() || !createForm.operation_reason.trim()" @click="createProfile">创建</el-button></template>
    </el-dialog>

    <el-dialog v-model="retrievalDialog" :title="retrievalEditor.mode === 'create' ? '新建 Retrieval Profile' : '编辑 Retrieval 草稿'" width="760px">
      <el-form label-position="top">
        <div v-if="retrievalEditor.mode === 'create'" class="schema-grid">
          <el-form-item label="名称"><el-input v-model="retrievalEditor.name" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="retrievalEditor.description" /></el-form-item>
        </div>
        <el-form-item label="检索参数 JSON"><el-input v-model="retrievalEditor.config" type="textarea" :rows="18" /></el-form-item>
        <el-form-item label="操作原因"><el-input v-model="retrievalEditor.operation_reason" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="retrievalDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!retrievalEditor.operation_reason.trim() || (retrievalEditor.mode === 'create' && !retrievalEditor.name.trim())" @click="saveRetrieval">保存草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="knowledgeBaseDialog" :title="knowledgeBaseEditor.mode === 'create' ? '新建知识库' : '编辑知识库草稿'" width="820px">
      <el-form label-position="top">
        <div v-if="knowledgeBaseEditor.mode === 'create'" class="schema-grid">
          <el-form-item label="名称"><el-input v-model="knowledgeBaseEditor.name" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="knowledgeBaseEditor.description" /></el-form-item>
        </div>
        <el-form-item label="默认 Retrieval 发布版本">
          <el-select v-model="knowledgeBaseEditor.default_retrieval_revision_id" filterable style="width: 100%">
            <template v-for="profile in retrievalProfiles" :key="profile.id">
              <el-option v-for="item in profile.revisions?.filter((entry:any) => entry.status === 'published') || []" :key="item.id" :label="`${profile.name} · v${item.version}`" :value="item.id" />
            </template>
          </el-select>
        </el-form-item>
        <div class="schema-grid">
          <el-form-item label="摄取策略 JSON"><el-input v-model="knowledgeBaseEditor.ingestion_policy" type="textarea" :rows="15" /></el-form-item>
          <el-form-item label="文档成员 JSON"><el-input v-model="knowledgeBaseEditor.members" type="textarea" :rows="15" /></el-form-item>
        </div>
        <el-form-item label="操作原因"><el-input v-model="knowledgeBaseEditor.operation_reason" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="knowledgeBaseDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!knowledgeBaseEditor.operation_reason.trim() || !knowledgeBaseEditor.default_retrieval_revision_id || (knowledgeBaseEditor.mode === 'create' && !knowledgeBaseEditor.name.trim())" @click="saveKnowledgeBase">保存草稿</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.agent-config { padding-bottom: 88px; }
.header-actions, .selector-band, .workflow-actions, .prompt-controls { display: flex; align-items: center; gap: 10px; }
.selector-band { margin: 18px 0 8px; padding: 14px; border: 1px solid #dfe3e8; border-radius: 6px; background: #fff; }
.selector-band code { margin-left: auto; color: #667085; }
.config-tabs { margin-top: 14px; }
.release-grid, .editor-grid, .two-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.release-card, .preview-panel { padding: 20px; }
.release-card h3, .preview-panel h3, .surface-header h3 { margin: 0 0 14px; }
dl { margin: 0; } dl div { display: grid; grid-template-columns: 110px 1fr; padding: 9px 0; border-bottom: 1px solid #eef0f3; } dt { color: #667085; } dd { margin: 0; }
.hash { overflow-wrap: anywhere; font-family: ui-monospace, monospace; }
.gate { margin-top: 10px; }
.workflow-actions { margin: 18px 0; }
.version-table { margin-top: 16px; }
.editor-panel { padding: 18px; border: 1px solid #dfe3e8; border-radius: 6px; background: #fff; }
.panel-title, .surface-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.panel-title h3 { margin: 0 0 12px; }
.token-total { margin: 18px 0; font-size: 34px; font-weight: 700; }.token-total small { display: block; color: #667085; font-size: 12px; font-weight: 400; }
.prompt-layout { display: grid; grid-template-columns: 245px 1fr; gap: 16px; }
.prompt-layout aside { display: flex; flex-direction: column; gap: 4px; padding: 8px; border: 1px solid #dfe3e8; border-radius: 6px; background: #fff; }
.prompt-layout aside button { padding: 11px; border: 0; border-radius: 4px; background: transparent; color: #344054; text-align: left; cursor: pointer; }
.prompt-layout aside button.active { color: #1d4ed8; background: #eff6ff; font-weight: 600; }
.prompt-editor label { display: block; margin: 14px 0 7px; color: #475467; font-size: 13px; font-weight: 600; }
.schema-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.prompt-controls { margin-top: 14px; }
.surface-header { padding: 16px 18px; border-bottom: 1px solid #e5e7eb; }.surface-header h3 { margin: 0; }.surface-header span { color: #667085; font-size: 12px; }
.binding-editor { margin-bottom: 16px; }.binding-editor p { margin: 4px 0 12px; color: #667085; font-size: 12px; }
.sticky-save { position: fixed; right: 28px; bottom: 20px; z-index: 5; display: flex; align-items: center; gap: 20px; padding: 12px 14px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; box-shadow: 0 8px 22px rgb(15 23 42 / 14%); color: #667085; font-size: 13px; }
</style>
