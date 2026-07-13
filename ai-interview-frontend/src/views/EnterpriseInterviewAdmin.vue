<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTabPane,
  ElTabs,
  ElTag,
} from 'element-plus';
import { CopyDocument, Refresh, VideoPlay } from '@element-plus/icons-vue';
import { useAuthStore } from '@/store/modules/auth';
import {
  cloneInterviewTemplateApi,
  createEvaluationDatasetApi,
  createEvaluationRunApi,
  getEvaluationDatasetsApi,
  getEvaluationRunsApi,
  getInterviewRubricsApi,
  getInterviewTemplatesApi,
  type EvaluationDataset,
  type EvaluationRun,
  type InterviewRubric,
  type InterviewTemplate,
} from '@/api/modules/interviewEnterprise';

const authStore = useAuthStore();
const loading = ref(false);
const templates = ref<InterviewTemplate[]>([]);
const rubrics = ref<InterviewRubric[]>([]);
const datasets = ref<EvaluationDataset[]>([]);
const runs = ref<EvaluationRun[]>([]);
const datasetForm = ref({
  name: '',
  description: '',
  visibility: 'private' as 'private' | 'shared',
});
const runForm = ref({
  dataset: null as number | null,
  template: null as number | null,
});

const canManage = computed(() => {
  const role = (authStore.user?.role || '').toLowerCase();
  return ['admin', 'hr'].includes(role);
});

const loadAll = async () => {
  if (!canManage.value) return;
  loading.value = true;
  try {
    const [templateRes, rubricRes, datasetRes, runRes] = await Promise.all([
      getInterviewTemplatesApi(),
      getInterviewRubricsApi(),
      getEvaluationDatasetsApi(),
      getEvaluationRunsApi(),
    ]);
    templates.value = templateRes.results;
    rubrics.value = rubricRes.results;
    datasets.value = datasetRes.results;
    runs.value = runRes.results;
  } finally {
    loading.value = false;
  }
};

const cloneTemplate = async (template: InterviewTemplate) => {
  await cloneInterviewTemplateApi(template.id);
  ElMessage.success('已复制模板，可在后台继续编辑');
  await loadAll();
};

const createDataset = async () => {
  if (!datasetForm.value.name.trim()) {
    ElMessage.warning('请输入数据集名称');
    return;
  }
  await createEvaluationDatasetApi({
    name: datasetForm.value.name,
    description: datasetForm.value.description,
    visibility: datasetForm.value.visibility,
    cases: [],
  });
  datasetForm.value.name = '';
  datasetForm.value.description = '';
  ElMessage.success('评估数据集已创建');
  await loadAll();
};

const createRun = async () => {
  if (!runForm.value.dataset) {
    ElMessage.warning('请选择评估数据集');
    return;
  }
  await createEvaluationRunApi({
    dataset: runForm.value.dataset,
    template: runForm.value.template,
  });
  ElMessage.success('评估任务已提交');
  await loadAll();
};

onMounted(loadAll);
</script>

<template>
  <div class="enterprise-page">
    <div class="page-heading">
      <div>
        <h1>企业面试体系</h1>
        <p>管理面试模板、评分量表、校准数据集和离线评估运行。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <div v-if="!canManage" class="empty-state">
      当前账号没有企业面试体系管理权限。
    </div>

    <el-tabs v-else v-loading="loading" class="admin-tabs">
      <el-tab-pane label="面试模板">
        <el-table :data="templates" stripe>
          <el-table-column prop="name" label="模板" min-width="180" />
          <el-table-column label="量表" min-width="180">
            <template #default="{ row }">{{ row.rubric_detail?.name || row.rubric }}</template>
          </el-table-column>
          <el-table-column label="范围" width="100">
            <template #default="{ row }">
              <el-tag :type="row.visibility === 'system' ? 'success' : 'info'">{{ row.visibility }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="90">
            <template #default="{ row }">{{ row.stages?.length || 0 }}</template>
          </el-table-column>
          <el-table-column label="RAG" width="90">
            <template #default="{ row }">
              <el-tag :type="row.require_rag ? 'warning' : 'info'">{{ row.require_rag ? '强约束' : '可选' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button :icon="CopyDocument" size="small" @click="cloneTemplate(row)">复制编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="评分量表">
        <el-table :data="rubrics" stripe>
          <el-table-column prop="name" label="量表" min-width="180" />
          <el-table-column prop="version" label="版本" width="90" />
          <el-table-column label="维度" width="100">
            <template #default="{ row }">{{ row.dimensions?.length || 0 }}</template>
          </el-table-column>
          <el-table-column label="范围" width="100">
            <template #default="{ row }">
              <el-tag :type="row.visibility === 'system' ? 'success' : 'info'">{{ row.visibility }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="280" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="离线评估">
        <div class="eval-grid">
          <section class="panel">
            <h2>创建数据集</h2>
            <el-form :model="datasetForm" label-position="top">
              <el-form-item label="名称">
                <el-input v-model="datasetForm.name" placeholder="例如 AI应用开发匿名化样例集" />
              </el-form-item>
              <el-form-item label="说明">
                <el-input v-model="datasetForm.description" type="textarea" :rows="3" />
              </el-form-item>
              <el-form-item label="范围">
                <el-select v-model="datasetForm.visibility" style="width: 100%;">
                  <el-option label="私有" value="private" />
                  <el-option label="共享" value="shared" />
                </el-select>
              </el-form-item>
              <el-button type="primary" @click="createDataset">创建</el-button>
            </el-form>
          </section>

          <section class="panel">
            <h2>运行评估</h2>
            <el-form :model="runForm" label-position="top">
              <el-form-item label="数据集">
                <el-select v-model="runForm.dataset" style="width: 100%;" placeholder="选择数据集">
                  <el-option v-for="item in datasets" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="模板">
                <el-select v-model="runForm.template" style="width: 100%;" clearable placeholder="可选">
                  <el-option v-for="item in templates" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-button type="primary" :icon="VideoPlay" @click="createRun">运行</el-button>
            </el-form>
          </section>
        </div>

        <el-table :data="runs" stripe class="run-table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'succeeded' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="摘要" min-width="240">
            <template #default="{ row }">{{ row.summary }}</template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误" min-width="220" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.enterprise-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-heading,
.admin-tabs,
.empty-state,
.panel {
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

.page-heading h1,
.panel h2 {
  margin: 0 0 6px;
  color: #1f2d3d;
}

.page-heading h1 {
  font-size: 22px;
}

.page-heading p {
  margin: 0;
  color: #606266;
}

.admin-tabs {
  padding: 12px;
}

.empty-state {
  padding: 28px;
  color: #909399;
}

.eval-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.panel {
  padding: 16px;
}

.panel h2 {
  font-size: 16px;
}

.run-table {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .eval-grid {
    grid-template-columns: 1fr;
  }
}
</style>
