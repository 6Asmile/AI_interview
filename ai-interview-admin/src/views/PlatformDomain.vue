<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';

const route = useRoute();
const loading = ref(false);
const data = ref<any>(null);
const saving = ref(false);
const loadError = ref('');
const resumeForm = ref({
  enabled: true,
  enabled_templates: [] as string[],
  renderer_version: '2.8',
  ats_rules_version: '1.0.0',
  render_timeout_seconds: 20,
  max_input_bytes: 2_000_000,
});

const config = computed(() => {
  const name = String(route.name || '');
  return ({
    CareerConfig: { title: '职业配置', endpoint: '/career-config/', description: '技能分类、岗位匹配、成长规则与计划模板。' },
    ResumeConfig: { title: '简历配置', endpoint: '/resume-config/', description: '六套母版、RenderCV 版本、ATS 规则和渲染任务健康；不展示用户正文。' },
    Companies: { title: '企业认证', endpoint: '/companies/', description: '企业成员关系之外的独立平台认证与审计。' },
    Jobs: { title: '岗位审核', endpoint: '/jobs/', description: '岗位修订审核、发布与下架。' },
    CommunityControl: { title: '社区治理', endpoint: '/community/moderation/', description: '匿名内容、风险发现、举报与申诉处置。' },
    PlatformEvents: { title: '事件与队列', endpoint: '/operations/events/', description: '区分 PostgreSQL Outbox、Operation Dispatch 与 RabbitMQ DLQ，查看积压并审计数据库事件重放。' },
    Reliability: { title: '可靠性中心', endpoint: '/reliability/', description: '查看 Redis 三故障域、版本化队列、租约积压、降级契约与外部验证边界。' },
  } as Record<string, any>)[name];
});

const rows = computed(() => Array.isArray(data.value) ? data.value : []);
const summary = computed(() => Array.isArray(data.value) ? null : data.value);
const databaseDeadLetters = computed(() => (
  Array.isArray(data.value?.database_outbox_dead_letters)
    ? data.value.database_outbox_dead_letters
    : []
));
const dispatchDeadLetters = computed(() => (
  Array.isArray(data.value?.operation_dispatch_dead_letters)
    ? data.value.operation_dispatch_dead_letters
    : []
));
const eventStatusGroups = computed(() => [
  { key: 'operations', label: 'Operation', values: data.value?.operations || {} },
  { key: 'operation_dispatch', label: '命令 Dispatch', values: data.value?.operation_dispatch || {} },
  { key: 'database_outbox', label: '领域事件 Outbox', values: data.value?.database_outbox || {} },
  { key: 'consumer_inbox', label: '消费者 Inbox', values: data.value?.consumer_inbox || {} },
]);
const durableRows = computed(() => Object.entries(data.value?.durable_async || {}).map(([kind, value]: [string, any]) => ({
  kind,
  total: Number(value?.total || 0),
  actionable: Number(value?.actionable || 0),
  oldest_age_seconds: Number(value?.oldest_actionable_age_seconds || 0),
  statuses: value?.by_status || {},
})));
const degradationRows = computed(() => Object.entries(data.value?.degradation_contract || {}).map(([dependency, behavior]) => ({
  dependency,
  behavior,
})));

const formatAge = (seconds: number) => {
  if (!seconds) return '无积压';
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
};
const statusSummary = (values: Record<string, number>) => Object.entries(values || {})
  .filter(([, count]) => Number(count) > 0)
  .map(([name, count]) => `${name} ${count}`)
  .join(' · ') || '暂无记录';

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    data.value = await api.get(config.value.endpoint);
    if (route.name === 'ResumeConfig' && data.value?.policy) {
      resumeForm.value = {
        enabled: data.value.policy.enabled !== false,
        enabled_templates: [...(data.value.policy.config?.enabled_templates || [])],
        renderer_version: data.value.policy.config?.renderer_version || data.value.renderer?.version || '2.8',
        ats_rules_version: data.value.policy.config?.ats_rules_version || '1.0.0',
        render_timeout_seconds: Number(data.value.policy.config?.render_timeout_seconds || 20),
        max_input_bytes: Number(data.value.policy.config?.max_input_bytes || 2_000_000),
      };
    }
  } catch (error: any) {
    loadError.value = error?.response?.data?.message || error?.message || '无法加载当前数据，请检查网络或权限后重试。';
  } finally {
    loading.value = false;
  }
}

async function saveResumeConfig() {
  const reason = await ElMessageBox.prompt('请输入配置变更原因，前后快照会写入审计链。', '发布简历运行配置', {
    inputPattern: /.+/,
    inputErrorMessage: '必须填写操作原因',
  }).then(result => result.value).catch(() => '');
  if (!reason) return;
  saving.value = true;
  try {
    await api.post('/resume-config/', {
      operation_reason: reason,
      enabled: resumeForm.value.enabled,
      config: {
        enabled_templates: resumeForm.value.enabled_templates,
        renderer_version: resumeForm.value.renderer_version,
        ats_rules_version: resumeForm.value.ats_rules_version,
        render_timeout_seconds: resumeForm.value.render_timeout_seconds,
        max_input_bytes: resumeForm.value.max_input_bytes,
      },
    });
    ElMessage.success('简历配置已保存并完成审计');
    await load();
  } finally {
    saving.value = false;
  }
}

async function decide(row: any, decision: string) {
  const reason = await ElMessageBox.prompt('请输入本次操作原因，内容会进入审计链。', '确认操作', {
    inputPattern: /.+/,
    inputErrorMessage: '必须填写操作原因',
  }).then(result => result.value).catch(() => '');
  if (!reason) return;
  const resource = route.name === 'Companies' ? 'companies'
    : route.name === 'Jobs' ? 'jobs'
      : 'community/moderation';
  await api.post(`/${resource}/${row.id}/${decision}/`, { operation_reason: reason });
  ElMessage.success('操作已记录');
  await load();
}

async function replay(row: any) {
  const reason = await ElMessageBox.prompt('请输入重放原因。该操作只重置 PostgreSQL IntegrationOutbox，会保留原 event_id 并由 Inbox 去重。', '重放数据库 Outbox', {
    inputPattern: /.+/,
    inputErrorMessage: '必须填写操作原因',
  }).then(result => result.value).catch(() => '');
  if (!reason) return;
  await api.post(`/operations/events/${row.event_id}/replay/`, { operation_reason: reason });
  ElMessage.success('事件已进入待投递队列');
  await load();
}

onMounted(load);
watch(() => route.name, load);
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div><h1>{{ config.title }}</h1><p>{{ config.description }}</p></div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </header>
    <el-alert
      v-if="loadError"
      class="load-error"
      type="error"
      :closable="false"
      show-icon
      title="数据加载失败"
      :description="loadError"
      aria-live="polite"
    >
      <template #default><el-button size="small" @click="load">重试</el-button></template>
    </el-alert>
    <el-table v-if="!['PlatformEvents', 'Reliability'].includes(String(route.name)) && rows.length" :data="rows" stripe border>
      <el-table-column prop="name" label="名称" min-width="180">
        <template #default="{ row }">{{ row.name || row.title || row.event_type || row.id }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column prop="risk_level" label="风险" width="100" />
      <el-table-column label="标识" min-width="220"><template #default="{ row }">{{ row.id }}</template></el-table-column>
      <el-table-column v-if="['Companies','Jobs','CommunityControl'].includes(String(route.name))" label="操作" width="230">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="decide(row, 'approve')">通过</el-button>
          <el-button size="small" type="danger" @click="decide(row, 'reject')">拒绝</el-button>
          <el-button v-if="route.name === 'CommunityControl'" size="small" @click="decide(row, 'hide')">隐藏</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="route.name === 'PlatformEvents' && summary" v-loading="loading" class="operations-view">
      <section class="ops-section" aria-labelledby="database-events-title">
        <div class="section-heading">
          <div>
            <h2 id="database-events-title">数据库可靠性状态</h2>
            <p>Operation 是用户可见状态，Dispatch 驱动命令，Outbox / Inbox 保护领域事件与幂等消费。</p>
          </div>
          <span class="oldest-age">最早待投递：{{ summary.oldest_pending_at || '无' }}</span>
        </div>
        <dl class="status-band">
          <div v-for="group in eventStatusGroups" :key="group.key">
            <dt>{{ group.label }}</dt>
            <dd>{{ statusSummary(group.values) }}</dd>
          </div>
        </dl>
      </section>

      <section class="ops-section" aria-labelledby="database-dead-title">
        <div class="section-heading">
          <div>
            <h2 id="database-dead-title">PostgreSQL Outbox Dead</h2>
            <p>这些是数据库事件投递记录，不是 RabbitMQ DLQ 消息。重放会保留 event_id 以供 Inbox 去重。</p>
          </div>
        </div>
        <el-table v-if="databaseDeadLetters.length" :data="databaseDeadLetters" stripe>
          <el-table-column prop="event_type" label="事件类型" min-width="210" />
          <el-table-column prop="event_id" label="Event ID" min-width="290" />
          <el-table-column prop="attempts" label="投递次数" width="100" />
          <el-table-column prop="created_at" label="创建时间" min-width="180" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }"><el-button size="small" @click="replay(row)">重放 Outbox</el-button></template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="没有数据库 Outbox Dead 记录" />
      </section>

      <section class="ops-section" aria-labelledby="dispatch-dead-title">
        <div class="section-heading"><div><h2 id="dispatch-dead-title">Operation Dispatch Dead</h2><p>命令超过数据库发布尝试上限后进入 Dead；它与 Broker DLQ 仍是两条独立故障链。</p></div></div>
        <el-table v-if="dispatchDeadLetters.length" :data="dispatchDeadLetters" stripe>
          <el-table-column prop="operation_id" label="Operation ID" min-width="290" />
          <el-table-column prop="queue" label="目标队列" min-width="230" />
          <el-table-column prop="routing_key" label="Routing Key" min-width="170" />
          <el-table-column prop="attempts" label="尝试" width="80" />
        </el-table>
        <el-empty v-else description="没有 Operation Dispatch Dead 记录" />
      </section>

      <section class="ops-section broker-section" aria-labelledby="broker-dlq-title">
        <div class="section-heading"><div><h2 id="broker-dlq-title">RabbitMQ Broker DLQ</h2><p>{{ summary.broker_dead_letters?.message }}</p></div><el-tag type="warning">{{ summary.broker_dead_letters?.status }}</el-tag></div>
        <el-alert type="warning" :closable="false" show-icon title="受控 Broker DLQ 重放尚未在管理端开放" description="当前深度、Unacked 与 Consumer 由 RabbitMQ Prometheus 指标提供。本页不会把数据库 Dead 记录冒充为 Broker 死信。" />
        <ul class="queue-list"><li v-for="queue in summary.broker_dead_letters?.queues || []" :key="queue"><code>{{ queue }}</code></li></ul>
      </section>
    </div>

    <div v-if="route.name === 'Reliability' && summary" v-loading="loading" class="reliability-view">
      <section class="ops-section" aria-labelledby="durable-runtime-title">
        <div class="section-heading"><div><h2 id="durable-runtime-title">耐久异步骨架</h2><p>聚合状态不含用户、租户、Payload 或错误正文，可用于判断积压与过期租约。</p></div><el-tag :type="summary.stale_operation_leases ? 'danger' : 'success'">过期租约 {{ summary.stale_operation_leases || 0 }}</el-tag></div>
        <el-table v-if="durableRows.length" :data="durableRows" stripe>
          <el-table-column prop="kind" label="记录类型" min-width="190" />
          <el-table-column prop="total" label="总数" width="90" />
          <el-table-column prop="actionable" label="待处理" width="100" />
          <el-table-column label="最早积压" width="150"><template #default="{ row }">{{ formatAge(row.oldest_age_seconds) }}</template></el-table-column>
          <el-table-column label="状态分布" min-width="260"><template #default="{ row }"><span class="wrap-text">{{ statusSummary(row.statuses) }}</span></template></el-table-column>
        </el-table>
        <el-empty v-else description="暂无耐久异步状态" />
      </section>

      <section class="ops-section" aria-labelledby="degradation-title">
        <div class="section-heading"><div><h2 id="degradation-title">故障降级契约</h2><p>PostgreSQL 仍是唯一业务事实源；Redis、RabbitMQ 与索引故障不能伪造成功。</p></div></div>
        <dl class="contract-list"><div v-for="row in degradationRows" :key="row.dependency"><dt>{{ row.dependency }}</dt><dd>{{ row.behavior }}</dd></div></dl>
      </section>

      <section class="ops-section" aria-labelledby="topology-title">
        <div class="section-heading"><div><h2 id="topology-title">版本化 Celery 拓扑</h2><p>稳定 Exchange 与 <code>ifaceoff.{{ summary.celery_topology?.version }}.*</code> 队列分开演进，Publisher 拥有独立故障域。</p></div><el-tag>{{ summary.celery_topology?.version }}</el-tag></div>
        <dl class="topology-facts"><div><dt>Publisher</dt><dd><code>{{ summary.celery_topology?.publisher_queue }}</code></dd></div><div><dt>Broker DLQ 重放</dt><dd>{{ summary.celery_topology?.broker_dlq_replay }}</dd></div><div><dt>生产 HA</dt><dd>{{ summary.runtime_verification?.production_ha }}</dd></div></dl>
        <ul class="queue-list main-queues"><li v-for="queue in summary.celery_topology?.main_queues || []" :key="queue"><code>{{ queue }}</code></li></ul>
      </section>
    </div>
    <el-card v-if="route.name === 'ResumeConfig' && summary" v-loading="loading" shadow="never" class="resume-config-card">
      <template #header>
        <div class="config-heading">
          <div>
            <strong>运行配置</strong>
            <span>JSON Resume {{ summary.schema?.version }} · {{ summary.renderer?.name }} {{ summary.renderer?.version }}</span>
          </div>
          <el-switch v-model="resumeForm.enabled" active-text="启用" inactive-text="停用" />
        </div>
      </template>
      <el-form label-position="top">
        <el-form-item label="启用母版">
          <el-checkbox-group v-model="resumeForm.enabled_templates" class="template-options">
            <el-checkbox v-for="item in summary.templates || []" :key="item.key" :value="item.key">
              {{ item.name?.['zh-CN'] || item.key }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <div class="config-grid">
          <el-form-item label="渲染器版本">
            <el-input v-model="resumeForm.renderer_version" disabled />
          </el-form-item>
          <el-form-item label="ATS 规则版本">
            <el-input v-model="resumeForm.ats_rules_version" maxlength="40" />
          </el-form-item>
          <el-form-item label="渲染超时（秒）">
            <el-input-number v-model="resumeForm.render_timeout_seconds" :min="5" :max="60" />
          </el-form-item>
          <el-form-item label="最大结构化内容（字节）">
            <el-input-number v-model="resumeForm.max_input_bytes" :min="100000" :max="2000000" :step="100000" />
          </el-form-item>
        </div>
        <el-alert type="info" :closable="false" :title="summary.privacy_contract" />
        <div class="config-actions">
          <el-button type="primary" :loading="saving" :disabled="!resumeForm.enabled_templates.length" @click="saveResumeConfig">
            保存配置
          </el-button>
        </div>
      </el-form>
    </el-card>
    <el-empty
      v-else-if="!loading && !loadError && !rows.length && !summary"
      description="暂无可展示数据"
    />
  </section>
</template>

<style scoped>
.page { padding: 28px; }
.page-header { margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 24px; }
p { margin: 0; color: #667085; }
.load-error { margin-bottom: 18px; }
.operations-view, .reliability-view { display: grid; gap: 22px; }
.ops-section { min-width: 0; overflow: hidden; border: 1px solid #dfe3e8; border-radius: 12px; background: #fff; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 20px 22px; border-bottom: 1px solid #e8ebef; }
.section-heading > div { min-width: 0; }
.section-heading h2 { margin: 0 0 6px; color: #1f2937; font-size: 18px; }
.section-heading p { max-width: 78ch; line-height: 1.55; overflow-wrap: anywhere; }
.oldest-age { flex: 0 0 auto; color: #475467; font-size: 14px; }
.status-band { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; }
.status-band > div { min-width: 0; padding: 18px 20px; border-inline-end: 1px solid #e8ebef; }
.status-band > div:last-child { border-inline-end: 0; }
.status-band dt, .contract-list dt, .topology-facts dt { color: #475467; font-size: 13px; font-weight: 600; }
.status-band dd { margin: 8px 0 0; color: #101828; font-size: 15px; line-height: 1.45; overflow-wrap: anywhere; }
.broker-section :deep(.el-alert) { margin: 18px 22px 4px; }
.queue-list { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 22px 22px; padding: 0; list-style: none; }
.queue-list li { max-width: 100%; padding: 6px 9px; border: 1px solid #d0d5dd; border-radius: 6px; background: #f8fafc; }
code { overflow-wrap: anywhere; color: #344054; font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }
.contract-list { margin: 0; }
.contract-list > div, .topology-facts > div { display: grid; grid-template-columns: minmax(160px, .5fr) minmax(0, 1.5fr); gap: 18px; padding: 14px 22px; border-bottom: 1px solid #edf0f4; }
.contract-list > div:last-child, .topology-facts > div:last-child { border-bottom: 0; }
.contract-list dd, .topology-facts dd { margin: 0; color: #101828; overflow-wrap: anywhere; }
.topology-facts { margin: 0; }
.main-queues { padding-top: 18px; border-top: 1px solid #edf0f4; }
.wrap-text { overflow-wrap: anywhere; }
.resume-config-card { max-width: 960px; }
.config-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.config-heading > div { display: grid; gap: 4px; }
.config-heading span { color: #667085; font-size: 13px; }
.template-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px 20px; }
.config-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 20px; }
.config-actions { display: flex; justify-content: flex-end; margin-top: 20px; }
@media (max-width: 760px) {
  .template-options, .config-grid, .status-band { grid-template-columns: 1fr; }
  .status-band > div { border-inline-end: 0; border-bottom: 1px solid #e8ebef; }
  .status-band > div:last-child { border-bottom: 0; }
  .section-heading { flex-direction: column; }
  .contract-list > div, .topology-facts > div { grid-template-columns: 1fr; gap: 6px; }
}
</style>
