<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '@/api';

const loading = ref(true);
const summary = ref<Record<string, number>>({});
const metrics = [
  ['candidates', '候选人账号', '仅账号元数据'],
  ['running_interviews', '进行中面试', '不展示回答正文'],
  ['pending_knowledge_reviews', '待审知识版本', '审批后才可检索'],
  ['failed_tasks', '失败任务', '可在任务中心诊断'],
  ['failed_agent_runs', '失败 Agent Run', '查看节点降级原因'],
  ['open_message_reports', '待处理举报', '社区与私信治理'],
  ['pending_privacy_requests', '隐私请求', '导出或注销申请'],
] as const;
onMounted(async () => { try { summary.value = await api.get('/dashboard/summary/'); } finally { loading.value = false; } });
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="page-header"><div><h1>运行概览</h1><p>聚合真实业务状态，不展示示例指标或候选人私密内容。</p></div><el-tag effect="plain">员工身份域</el-tag></header>
    <section class="metric-band">
      <div v-for="item in metrics.slice(0, 4)" :key="item[0]" class="metric"><span>{{ item[1] }}</span><strong>{{ summary[item[0]] || 0 }}</strong><small>{{ item[2] }}</small></div>
    </section>
    <section class="dashboard-list">
      <div v-for="item in metrics.slice(4)" :key="item[0]"><span>{{ item[1] }}</span><strong :class="{ 'danger-text': summary[item[0]] }">{{ summary[item[0]] || 0 }}</strong><small>{{ item[2] }}</small></div>
    </section>
    <section class="action-inbox"><h2>运营待办</h2><div class="action-grid"><router-link v-if="summary.pending_knowledge_reviews" to="/knowledge"><strong>{{summary.pending_knowledge_reviews}}</strong><span>待审批知识版本</span></router-link><router-link v-if="summary.failed_agent_runs" to="/agent-runs"><strong>{{summary.failed_agent_runs}}</strong><span>失败 Agent Run</span></router-link><router-link v-if="summary.failed_tasks" to="/operations"><strong>{{summary.failed_tasks}}</strong><span>失败异步任务</span></router-link><router-link v-if="summary.open_message_reports" to="/moderation"><strong>{{summary.open_message_reports}}</strong><span>待处理举报</span></router-link><router-link v-if="summary.pending_privacy_requests" to="/candidates"><strong>{{summary.pending_privacy_requests}}</strong><span>待处理隐私请求</span></router-link><div v-if="!summary.pending_knowledge_reviews&&!summary.failed_agent_runs&&!summary.failed_tasks&&!summary.open_message_reports&&!summary.pending_privacy_requests" class="all-clear"><strong>当前没有阻塞性运营待办</strong><span>后台会持续聚合真实业务状态。</span></div></div></section>
  </div>
</template>

<style scoped>
.dashboard-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }
.dashboard-list > div { padding: 18px; border: 1px solid #dfe3e8; border-left: 4px solid #16a34a; border-radius: 4px; background: #fff; }
.dashboard-list span, .dashboard-list small { display: block; color: #667085; }
.dashboard-list strong { display: block; margin: 8px 0; font-size: 24px; }
.action-inbox{margin-top:28px}.action-inbox h2{font-size:18px}.action-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.action-grid>a,.all-clear{display:flex;align-items:center;gap:14px;padding:16px;border:1px solid #dfe3e8;background:#fff;text-decoration:none}.action-grid>a:hover{border-color:#1d4ed8}.action-grid strong{font-size:22px}.action-grid span{color:#667085}.all-clear{grid-column:1/-1;display:grid}
</style>
