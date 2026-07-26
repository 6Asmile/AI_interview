<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';

const route = useRoute();
const loading = ref(false);
const data = ref<any>(null);

const config = computed(() => {
  const name = String(route.name || '');
  return ({
    CareerConfig: { title: '职业配置', endpoint: '/career-config/', description: '技能分类、岗位匹配、成长规则与计划模板。' },
    Companies: { title: '企业认证', endpoint: '/companies/', description: '企业成员关系之外的独立平台认证与审计。' },
    Jobs: { title: '岗位审核', endpoint: '/jobs/', description: '岗位修订审核、发布与下架。' },
    CommunityControl: { title: '社区治理', endpoint: '/community/moderation/', description: '匿名内容、风险发现、举报与申诉处置。' },
    PlatformEvents: { title: '事件与队列', endpoint: '/operations/events/', description: 'Outbox、Inbox、最老消息与死信受控重放。' },
    Reliability: { title: '可靠性中心', endpoint: '/reliability/', description: '准入阈值、降级契约与运行策略。' },
  } as Record<string, any>)[name];
});

const rows = computed(() => Array.isArray(data.value) ? data.value : []);
const summary = computed(() => Array.isArray(data.value) ? null : data.value);
const deadLetters = computed(() => Array.isArray(data.value?.dead_letters) ? data.value.dead_letters : []);

async function load() {
  loading.value = true;
  try {
    data.value = await api.get(config.value.endpoint);
  } finally {
    loading.value = false;
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
  const reason = await ElMessageBox.prompt('请输入重放原因。该操作会保留原 event_id，并由消费者 Inbox 去重。', '重放死信', {
    inputPattern: /.+/,
    inputErrorMessage: '必须填写操作原因',
  }).then(result => result.value).catch(() => '');
  if (!reason) return;
  await api.post(`/operations/events/${row.event_id}/replay/`, { operation_reason: reason });
  ElMessage.success('事件已进入待投递队列');
  await load();
}

onMounted(load);
</script>

<template>
  <section class="page">
    <header>
      <div><h1>{{ config.title }}</h1><p>{{ config.description }}</p></div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </header>
    <el-table v-if="rows.length" :data="rows" stripe border>
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
    <el-table v-if="route.name === 'PlatformEvents' && deadLetters.length" :data="deadLetters" stripe border class="dead-table">
      <el-table-column prop="event_type" label="死信事件" min-width="200" />
      <el-table-column prop="event_id" label="Event ID" min-width="290" />
      <el-table-column prop="attempts" label="投递次数" width="100" />
      <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" @click="replay(row)">重放</el-button></template></el-table-column>
    </el-table>
    <el-card v-if="!rows.length" v-loading="loading" shadow="never">
      <pre>{{ JSON.stringify(summary, null, 2) }}</pre>
    </el-card>
  </section>
</template>

<style scoped>
.page { padding: 28px; }
header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 24px; }
p { margin: 0; color: #667085; }
pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: #344054; font: 13px/1.65 ui-monospace, monospace; }
.dead-table { margin-bottom: 18px; }
</style>
