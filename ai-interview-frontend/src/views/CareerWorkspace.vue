<template>
  <div class="career-page">
    <header class="page-header">
      <div>
        <h1>求职工作台</h1>
        <p>统一维护可信职业事实、目标岗位、投递进度和面试后的补强任务。</p>
      </div>
      <el-button v-if="activeTab !== 'tasks'" type="primary" :icon="Plus" @click="openCreate">{{ createLabel }}</el-button>
    </header>
    <el-alert
      v-if="loadErrors.length"
      class="load-alert"
      type="warning"
      :title="`部分数据暂时不可用：${loadErrors.join('、')}`"
      :closable="false"
      show-icon
    />

    <el-tabs v-model="activeTab" class="workspace-tabs">
      <el-tab-pane label="职业事实" name="facts">
        <el-table :data="facts" v-loading="loading" empty-text="还没有职业事实">
          <el-table-column prop="title" label="事实" min-width="220" />
          <el-table-column prop="fact_type" label="类型" width="120">
            <template #default="{ row }">{{ factTypeText[row.fact_type] || row.fact_type }}</template>
          </el-table-column>
          <el-table-column prop="organization" label="组织/项目" min-width="160" />
          <el-table-column prop="source_type" label="来源" width="110" />
          <el-table-column label="确认状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.verification_status === 'confirmed' ? 'success' : row.verification_status === 'rejected' ? 'danger' : 'warning'">
                {{ row.verification_status === 'confirmed' ? '已确认' : row.verification_status === 'rejected' ? '已拒绝' : '待确认' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.verification_status !== 'confirmed'" link type="success" @click="confirmFact(row)">确认</el-button>
              <el-button link type="primary" @click="editFact(row)">编辑</el-button>
              <el-button link type="danger" @click="removeFact(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="目标岗位" name="targets">
        <el-table :data="targets" v-loading="loading" empty-text="还没有目标岗位">
          <el-table-column prop="company_name" label="公司" min-width="160" />
          <el-table-column prop="position_name" label="岗位" min-width="180" />
          <el-table-column prop="location" label="地点" width="120" />
          <el-table-column prop="deadline" label="截止日期" width="130" />
          <el-table-column prop="application_count" label="投递数" width="90" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '准备中' : '已归档' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="editTarget(row)">编辑</el-button>
              <el-button link type="danger" @click="removeTarget(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="投递管道" name="applications">
        <div class="pipeline" v-loading="loading">
          <section v-for="column in pipelineColumns" :key="column.value" class="pipeline-column">
            <header><strong>{{ column.label }}</strong><span>{{ applicationsByStatus[column.value]?.length || 0 }}</span></header>
            <el-empty v-if="!applicationsByStatus[column.value]?.length" :image-size="48" description="暂无" />
            <article v-for="item in applicationsByStatus[column.value] || []" :key="item.id" class="application-card">
              <strong>{{ item.job_target_detail.company_name }}</strong>
              <p>{{ item.job_target_detail.position_name }}</p>
              <el-select :model-value="item.status" size="small" @change="value => changeApplicationStatus(item, value)">
                <el-option v-for="option in applicationStatuses" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
              <small v-if="item.next_action_at">下一步 {{ formatDateTime(item.next_action_at) }}</small>
            </article>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="补强任务" name="tasks">
        <el-table :data="tasks" v-loading="loading" empty-text="暂时没有补强任务">
          <el-table-column prop="title" label="任务" min-width="260" />
          <el-table-column prop="dimension" label="能力维度" width="150" />
          <el-table-column prop="priority" label="优先级" width="100" />
          <el-table-column label="状态" width="150">
            <template #default="{ row }">
              <el-select :model-value="row.status" size="small" @change="value => changeTaskStatus(row, value)">
                <el-option label="待完成" value="todo" /><el-option label="进行中" value="doing" /><el-option label="已完成" value="done" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="due_at" label="计划完成" width="180"><template #default="{ row }">{{ row.due_at ? formatDateTime(row.due_at) : '-' }}</template></el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="factDialog" :title="factForm.id ? '编辑职业事实' : '新增职业事实'" width="620px">
      <el-form :model="factForm" label-width="90px">
        <el-form-item label="类型"><el-select v-model="factForm.fact_type"><el-option v-for="(label, value) in factTypeText" :key="value" :label="label" :value="value" /></el-select></el-form-item>
        <el-form-item label="标题"><el-input v-model="factForm.title" /></el-form-item>
        <el-form-item label="组织/项目"><el-input v-model="factForm.organization" /></el-form-item>
        <el-form-item label="角色"><el-input v-model="factForm.role" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="factForm.description" type="textarea" :rows="5" /></el-form-item>
        <el-form-item label="证据链接"><el-input v-model="factForm.source_url" placeholder="可选，GitHub 来源必须填写" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="factDialog=false">取消</el-button><el-button type="primary" @click="saveFact">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="targetDialog" :title="targetForm.id ? '编辑目标岗位' : '新增目标岗位'" width="680px">
      <el-form :model="targetForm" label-width="90px">
        <el-form-item label="公司"><el-input v-model="targetForm.company_name" /></el-form-item>
        <el-form-item label="岗位"><el-input v-model="targetForm.position_name" /></el-form-item>
        <el-form-item label="地点"><el-input v-model="targetForm.location" /></el-form-item>
        <el-form-item label="JD"><el-input v-model="targetForm.jd_text" type="textarea" :rows="8" /></el-form-item>
        <el-form-item label="来源链接"><el-input v-model="targetForm.source_url" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="targetDialog=false">取消</el-button><el-button type="primary" @click="saveTarget">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="applicationDialog" title="新增投递" width="560px">
      <el-form :model="applicationForm" label-width="90px">
        <el-form-item label="目标岗位"><el-select v-model="applicationForm.job_target" filterable><el-option v-for="target in targets" :key="target.id" :label="`${target.company_name} · ${target.position_name}`" :value="target.id" /></el-select></el-form-item>
        <el-form-item label="当前状态"><el-select v-model="applicationForm.status"><el-option v-for="option in applicationStatuses" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item>
        <el-form-item label="来源"><el-input v-model="applicationForm.source" placeholder="官网、内推、招聘平台等" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="applicationForm.notes" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="applicationDialog=false">取消</el-button><el-button type="primary" @click="saveApplication">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import {
  confirmCareerFactApi, createApplicationApi, createCareerFactApi, createJobTargetApi,
  deleteCareerFactApi, deleteJobTargetApi, getApplicationsApi, getCareerFactsApi,
  getJobTargetsApi, getLearningTasksApi, updateApplicationApi, updateCareerFactApi,
  updateJobTargetApi, updateLearningTaskApi,
  type ApplicationStatus, type CareerFact, type JobApplication, type JobTarget, type LearningTask,
} from '@/api/modules/career';
import { formatDateTime } from '@/utils/format';

const activeTab = ref('facts');
const loading = ref(false);
const facts = ref<CareerFact[]>([]);
const targets = ref<JobTarget[]>([]);
const applications = ref<JobApplication[]>([]);
const tasks = ref<LearningTask[]>([]);
const loadErrors = ref<string[]>([]);
const factDialog = ref(false);
const targetDialog = ref(false);
const applicationDialog = ref(false);
const factForm = reactive<any>({});
const targetForm = reactive<any>({});
const applicationForm = reactive<any>({ status: 'saved' });

const factTypeText: Record<string, string> = { summary: '个人总结', education: '教育', work: '工作', project: '项目', skill: '技能', certification: '证书', achievement: '成果', open_source: '开源' };
const applicationStatuses = [
  { value: 'saved', label: '待投递' }, { value: 'applied', label: '已投递' },
  { value: 'screening', label: '筛选中' }, { value: 'interview', label: '面试中' },
  { value: 'offer', label: 'Offer' }, { value: 'accepted', label: '已接受' },
  { value: 'rejected', label: '未通过' }, { value: 'withdrawn', label: '已撤回' },
] as Array<{ value: ApplicationStatus; label: string }>;
const pipelineColumns = applicationStatuses.filter(item => ['saved', 'applied', 'screening', 'interview', 'offer'].includes(item.value));
const applicationsByStatus = computed(() => Object.fromEntries(applicationStatuses.map(({ value }) => [value, applications.value.filter(item => item.status === value)])) as Record<ApplicationStatus, JobApplication[]>);
const createLabel = computed(() => activeTab.value === 'facts' ? '新增事实' : activeTab.value === 'targets' ? '新增岗位' : '新增投递');

async function loadAll() {
  loading.value = true;
  loadErrors.value = [];
  try {
    const results = await Promise.allSettled([getCareerFactsApi(), getJobTargetsApi(), getApplicationsApi(), getLearningTasksApi()]);
    const labels = ['职业事实', '目标岗位', '投递管道', '补强任务'];
    const targetsForResult = [facts, targets, applications, tasks] as Array<{ value: any[] }>;
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') targetsForResult[index].value = result.value;
      else loadErrors.value.push(labels[index]);
    });
  }
  finally { loading.value = false; }
}
onMounted(loadAll);

function reset(target: any, value: any) { Object.keys(target).forEach(key => delete target[key]); Object.assign(target, value); }
function openCreate() {
  if (activeTab.value === 'facts') { reset(factForm, { fact_type: 'project', title: '', organization: '', role: '', description: '', source_type: 'manual', source_url: '', skills: [], metrics: {} }); factDialog.value = true; }
  else if (activeTab.value === 'targets') { reset(targetForm, { company_name: '', position_name: '', location: '', jd_text: '', source_url: '', status: 'active', keywords: [] }); targetDialog.value = true; }
  else if (activeTab.value === 'applications') { reset(applicationForm, { job_target: targets.value[0]?.id, status: 'saved', source: '', notes: '' }); applicationDialog.value = true; }
}
function editFact(row: CareerFact) { reset(factForm, row); factDialog.value = true; }
function editTarget(row: JobTarget) { reset(targetForm, row); targetDialog.value = true; }
async function saveFact() { if (!factForm.title?.trim()) return ElMessage.warning('请填写事实标题'); factForm.id ? await updateCareerFactApi(factForm.id, factForm) : await createCareerFactApi(factForm); factDialog.value = false; await loadAll(); ElMessage.success('职业事实已保存'); }
async function saveTarget() { if (!targetForm.company_name?.trim() || !targetForm.position_name?.trim()) return ElMessage.warning('请填写公司和岗位'); targetForm.id ? await updateJobTargetApi(targetForm.id, targetForm) : await createJobTargetApi(targetForm); targetDialog.value = false; await loadAll(); ElMessage.success('目标岗位已保存'); }
async function saveApplication() { if (!applicationForm.job_target) return ElMessage.warning('请选择目标岗位'); await createApplicationApi(applicationForm); applicationDialog.value = false; await loadAll(); ElMessage.success('投递已加入管道'); }
async function confirmFact(row: CareerFact) { await confirmCareerFactApi(row.id); await loadAll(); }
async function removeFact(row: CareerFact) { await ElMessageBox.confirm(`删除“${row.title}”？`, '确认删除'); await deleteCareerFactApi(row.id); await loadAll(); }
async function removeTarget(row: JobTarget) { await ElMessageBox.confirm(`删除“${row.company_name} · ${row.position_name}”？`, '确认删除'); await deleteJobTargetApi(row.id); await loadAll(); }
async function changeApplicationStatus(item: JobApplication, value: ApplicationStatus) { await updateApplicationApi(item.id, { status: value }); await loadAll(); }
async function changeTaskStatus(item: LearningTask, value: LearningTask['status']) { await updateLearningTaskApi(item.id, { status: value }); await loadAll(); }
</script>

<style scoped>
.career-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }
.page-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }
.page-header p { margin: 8px 0 0; color: #667085; }
.workspace-tabs { margin-top: 18px; padding: 0 20px 20px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }
.load-alert { margin-top: 16px; }
.pipeline { display: grid; grid-template-columns: repeat(5, minmax(210px, 1fr)); gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.pipeline-column { min-height: 420px; padding: 12px; background: #f7f8fa; border: 1px solid #e5e7eb; border-radius: 6px; }
.pipeline-column > header { display: flex; justify-content: space-between; margin-bottom: 12px; color: #344054; }
.pipeline-column > header span { color: #667085; }
.application-card { margin-bottom: 10px; padding: 12px; background: #fff; border: 1px solid #dfe3ea; border-radius: 6px; }
.application-card strong, .application-card p, .application-card small { display: block; }
.application-card p { margin: 5px 0 10px; color: #475467; }
.application-card small { margin-top: 10px; color: #667085; }
@media (max-width: 760px) { .career-page { padding: 14px; } .page-header { align-items: flex-start; flex-direction: column; } .pipeline { grid-template-columns: repeat(5, 240px); } }
</style>
