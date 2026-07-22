<template>
  <div class="dashboard-page" v-loading="loading">
    <header class="dashboard-header">
      <div>
        <h1>求职概览</h1>
        <p>今天需要推进的投递、面试准备和能力补强都在这里。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Document" @click="router.push('/dashboard/resumes')">简历中心</el-button>
        <el-button type="primary" :icon="VideoCamera" @click="router.push('/dashboard/interviews')">开始面试</el-button>
      </div>
    </header>

    <section class="metrics-band">
      <div v-for="metric in metrics" :key="metric.label" class="metric-item">
        <span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.note }}</small>
      </div>
    </section>

    <div class="dashboard-grid">
      <section class="workspace-section">
        <header><div><h2>投递管道</h2><p>按当前阶段汇总真实投递记录</p></div><el-button link type="primary" @click="router.push('/dashboard/career')">管理管道</el-button></header>
        <div class="pipeline-summary">
          <div v-for="stage in pipelineStages" :key="stage.key" class="pipeline-stage">
            <span>{{ stage.label }}</span><strong>{{ dashboard?.pipeline?.[stage.key] || 0 }}</strong>
          </div>
        </div>
      </section>

      <section class="workspace-section">
        <header><div><h2>近期动作</h2><p>按时间排序的面试与跟进事项</p></div></header>
        <el-empty v-if="!dashboard?.upcoming_actions?.length" :image-size="64" description="暂无待办动作" />
        <div v-else class="action-list">
          <button v-for="item in dashboard.upcoming_actions" :key="item.application_id" @click="router.push('/dashboard/career')">
            <span><strong>{{ item.company_name }}</strong><small>{{ item.position_name }}</small></span>
            <time>{{ formatDateTime(item.next_action_at) }}</time>
          </button>
        </div>
      </section>

      <section class="workspace-section full-width">
        <header><div><h2>准备清单</h2><p>只根据你已确认的真实资料计算，不用简历数量代替准备质量</p></div><strong class="readiness-value">{{ readinessPercentage }}%</strong></header>
        <div class="quality-list">
          <button v-for="item in preparationActions" :key="item.label" class="preparation-action" @click="router.push(item.route)">
            <span :class="['action-state', { ready: item.ready }]">{{ item.ready ? '已完成' : '待完成' }}</span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.detail }}</small>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Document, VideoCamera } from '@element-plus/icons-vue';
import { getCareerDashboardApi, type CareerDashboard } from '@/api/modules/career';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const loading = ref(false);
const dashboard = ref<CareerDashboard | null>(null);
const pipelineStages = [
  { key: 'saved', label: '待投递' }, { key: 'applied', label: '已投递' },
  { key: 'screening', label: '筛选中' }, { key: 'interview', label: '面试中' },
  { key: 'offer', label: 'Offer' },
] as const;
const metrics = computed(() => [
  { label: '目标岗位', value: dashboard.value?.active_job_targets || 0, note: '准备中的岗位' },
  { label: '职业事实', value: dashboard.value?.confirmed_facts || 0, note: '已人工确认' },
  { label: '简历', value: dashboard.value?.resume_count || 0, note: '个人简历库' },
  { label: '补强任务', value: dashboard.value?.open_learning_tasks || 0, note: '来自面试复盘' },
]);
const hasStandardResume = computed(() => {
  const total = dashboard.value?.resume_count || 0;
  return total > 0 && (dashboard.value?.resumes_without_versions || 0) < total;
});
const preparationActions = computed(() => [
  {
    label: '确认职业事实', ready: (dashboard.value?.confirmed_facts || 0) > 0,
    detail: `${dashboard.value?.confirmed_facts || 0} 条已人工确认`, route: '/dashboard/career',
  },
  {
    label: '创建目标岗位', ready: (dashboard.value?.active_job_targets || 0) > 0,
    detail: `${dashboard.value?.active_job_targets || 0} 个准备中的真实岗位`, route: '/dashboard/career',
  },
  {
    label: '确认标准简历版本', ready: hasStandardResume.value,
    detail: hasStandardResume.value ? '已有可审计版本' : '仍需导入并确认结构', route: '/dashboard/resumes',
  },
]);
const readinessPercentage = computed(() => Math.round(preparationActions.value.filter(item => item.ready).length / preparationActions.value.length * 100));
onMounted(async () => { loading.value = true; try { dashboard.value = await getCareerDashboardApi(); } finally { loading.value = false; } });
</script>

<style scoped>
.dashboard-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }
.dashboard-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }
.dashboard-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }
.dashboard-header p { margin: 8px 0 0; color: #667085; }
.header-actions { display: flex; gap: 10px; }
.metrics-band { display: grid; grid-template-columns: repeat(4, 1fr); margin: 20px 0; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }
.metric-item { padding: 18px 20px; border-right: 1px solid #e8ebf0; }
.metric-item:last-child { border-right: 0; }
.metric-item span, .metric-item small { display: block; color: #667085; }
.metric-item strong { display: block; margin: 6px 0 2px; color: #101828; font-size: 28px; }
.dashboard-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.workspace-section { padding: 20px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }
.workspace-section > header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }
.workspace-section h2 { margin: 0; font-size: 18px; color: #1f2937; }
.workspace-section p { margin: 5px 0 0; color: #667085; font-size: 13px; }
.full-width { grid-column: 1 / -1; }
.pipeline-summary { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.pipeline-stage { padding: 14px; background: #f7f8fa; border-left: 3px solid #3b82f6; }
.pipeline-stage span { display: block; color: #667085; font-size: 13px; }
.pipeline-stage strong { display: block; margin-top: 6px; color: #1f2937; font-size: 22px; }
.action-list { display: flex; flex-direction: column; }
.action-list button { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border: 0; border-bottom: 1px solid #edf0f4; background: transparent; text-align: left; cursor: pointer; }
.action-list span strong, .action-list span small { display: block; }
.action-list span small, .action-list time { margin-top: 4px; color: #667085; font-size: 12px; }
.quality-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.preparation-action { display: grid; gap: 7px; padding: 16px; border: 1px solid #e1e6ee; border-radius: 6px; background: #fafbfc; text-align: left; cursor: pointer; }
.preparation-action:hover { border-color: #93b4ee; background: #f6f9ff; }
.preparation-action strong { color: #101828; font-size: 15px; }
.preparation-action small { color: #667085; }
.action-state { width: fit-content; padding: 2px 7px; color: #92400e; background: #fef3c7; font-size: 12px; }
.action-state.ready { color: #166534; background: #dcfce7; }
.readiness-value { color: #1d4ed8; font-size: 24px; }
@media (max-width: 900px) { .metrics-band { grid-template-columns: repeat(2, 1fr); } .dashboard-grid { grid-template-columns: 1fr; } .full-width { grid-column: auto; } .quality-list { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .dashboard-page { padding: 14px; } .dashboard-header { align-items: flex-start; flex-direction: column; } .pipeline-summary { grid-template-columns: repeat(2, 1fr); } }
</style>
