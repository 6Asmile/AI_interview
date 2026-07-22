<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';
import { staffAuth } from '@/auth';

const loading = ref(false);
const rows = ref<any[]>([]);
const filters = reactive({ search: '', status: '' });
const detail = ref<any>(null);
const drawer = ref(false);

const load = async () => {
  loading.value = true;
  try { rows.value = await api.get('/interviews/', { params: filters }); }
  finally { loading.value = false; }
};

const openDetail = async (row: any) => {
  const grant = sessionStorage.getItem(`break_glass_${row.candidate_id}`);
  detail.value = await api.get(`/interviews/${row.id}/`, { params: grant ? { grant_id: grant } : {} });
  drawer.value = true;
};

const terminate = async (row: any) => {
  const { value } = await ElMessageBox.prompt('请输入终止异常面试的原因', '终止面试', { inputType: 'textarea' });
  await api.post(`/interviews/${row.id}/terminate/`, { operation_reason: value }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  ElMessage.success('面试已终止，关联运行节点已标记。');
  drawer.value = false;
  await load();
};

onMounted(load);
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="page-header"><div><h1>面试会话</h1><p>查看阶段、能力覆盖和运行状态；候选人回答默认受严格授权保护。</p></div></header>
    <div class="toolbar"><el-input v-model="filters.search" clearable placeholder="候选人邮箱或岗位" style="width:300px" /><el-select v-model="filters.status" clearable placeholder="会话状态" style="width:150px"><el-option label="进行中" value="running" /><el-option label="已完成" value="finished" /><el-option label="已取消" value="canceled" /><el-option label="待开始" value="pending" /></el-select><el-button type="primary" @click="load">查询</el-button></div>
    <div class="data-surface"><el-table :data="rows">
      <el-table-column prop="candidate_email" label="候选人" min-width="220" /><el-table-column prop="job_position" label="岗位" min-width="160" />
      <el-table-column prop="current_stage" label="阶段" min-width="150" /><el-table-column label="问题/运行" width="110"><template #default="{row}">{{row.question_total}} / {{row.run_total}}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.status==='running'?'warning':row.status==='finished'?'success':'info'">{{row.status}}</el-tag></template></el-table-column>
      <el-table-column prop="last_activity_at" label="最近活动" min-width="175" /><el-table-column label="操作" width="150" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openDetail(row)">查看</el-button><el-button v-if="staffAuth.has('interview.operate')&&['running','pending'].includes(row.status)" link type="danger" @click="terminate(row)">终止</el-button></template></el-table-column>
    </el-table></div>
    <el-drawer v-model="drawer" title="面试审计详情" size="820px">
      <template v-if="detail"><el-descriptions :column="3" border><el-descriptions-item label="候选人">{{detail.candidate_email}}</el-descriptions-item><el-descriptions-item label="岗位">{{detail.job_position}}</el-descriptions-item><el-descriptions-item label="状态">{{detail.status}}</el-descriptions-item><el-descriptions-item label="阶段">{{detail.current_stage}}</el-descriptions-item><el-descriptions-item label="目标时长">{{detail.target_duration_minutes}} 分钟</el-descriptions-item><el-descriptions-item label="私密授权">{{detail.private_access?'已授权':'未授权'}}</el-descriptions-item></el-descriptions>
      <h3>能力覆盖</h3><pre class="json-view">{{JSON.stringify(detail.coverage_summary,null,2)}}</pre>
      <h3>问题与证据</h3><el-timeline><el-timeline-item v-for="question in detail.questions" :key="question.id" :timestamp="`第 ${question.sequence} 轮 · ${question.target_dimension||'未指定能力'}`"><div class="question-card"><strong>{{question.question_text}}</strong><p v-if="question.answer_text">{{question.answer_text}}</p><el-alert v-else-if="question.answer_protected" title="回答正文受保护，请先在候选人支持页申请严格授权" type="warning" :closable="false" /><div class="question-meta"><el-tag>{{question.generation_mode}}</el-tag><el-tag :type="question.validation_status==='validated'?'success':'info'">{{question.validation_status}}</el-tag><span>评分：{{question.score ?? '未评估'}}</span></div></div></el-timeline-item></el-timeline>
      <el-button v-if="staffAuth.has('interview.operate')&&['running','pending'].includes(detail.status)" type="danger" plain @click="terminate(detail)">终止异常会话</el-button></template>
    </el-drawer>
  </div>
</template>

<style scoped>
h3{margin:24px 0 12px}.json-view{max-height:240px;overflow:auto;padding:14px;background:#f6f8fb;border:1px solid #e1e6ed}.question-card{padding:14px;border:1px solid #e1e6ed;background:#fff}.question-card p{line-height:1.7;white-space:pre-wrap}.question-meta{display:flex;align-items:center;gap:8px;margin-top:12px;color:#667085}
</style>
