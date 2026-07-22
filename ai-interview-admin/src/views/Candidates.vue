<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';
import { staffAuth } from '@/auth';

const loading = ref(false);
const search = ref('');
const rows = ref<any[]>([]);
const detail = ref<any>(null);
const drawer = ref(false);
const privacyRows = ref<any[]>([]);
const privateAccessDialog = ref(false);
const breakGlass = reactive({ operation_reason: '', mfa_code: '' });

const load = async () => {
  loading.value = true;
  try {
    rows.value = await api.get('/candidates/', { params: { search: search.value } });
    if (staffAuth.has('privacy.manage')) privacyRows.value = await api.get('/privacy-requests/');
  } finally { loading.value = false; }
};

const openDetail = async (row: any) => {
  detail.value = await api.get(`/candidates/${row.id}/`);
  drawer.value = true;
};

const accountAction = async (row: any, action: string, label: string) => {
  const { value } = await ElMessageBox.prompt(`请输入${label}原因`, label, { inputType: 'textarea' });
  await api.post(`/candidates/${row.id}/${action}/`, { operation_reason: value }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  ElMessage.success(`${label}已完成。`);
  await load();
};

const grantPrivateAccess = async () => {
  const result = await api.post(`/candidates/${detail.value.id}/break-glass/`, breakGlass);
  sessionStorage.setItem(`break_glass_${detail.value.id}`, result.grant_id);
  privateAccessDialog.value = false;
  Object.assign(breakGlass, { operation_reason: '', mfa_code: '' });
  ElMessage.success('已获得 15 分钟限时只读授权，访问将完整审计。');
};

const decidePrivacy = async (item: any, decision: 'complete' | 'reject') => {
  const { value } = await ElMessageBox.prompt('请输入处理说明', decision === 'complete' ? '完成隐私请求' : '拒绝隐私请求', { inputType: 'textarea' });
  await api.post(`/privacy-requests/${item.id}/${decision}/`, { operation_reason: value }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  await load();
};

onMounted(load);
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="page-header"><div><h1>候选人支持</h1><p>默认仅展示账号与业务计数，简历、回答和音视频需要限时严格授权。</p></div></header>
    <div class="toolbar"><el-input v-model="search" clearable placeholder="搜索候选人邮箱" style="width:320px" @keyup.enter="load" /><el-button type="primary" @click="load">查询</el-button></div>
    <div class="data-surface"><el-table :data="rows">
      <el-table-column prop="email" label="邮箱" min-width="230" /><el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.status===1?'success':'danger'">{{row.status===1?'正常':'停用'}}</el-tag></template></el-table-column>
      <el-table-column label="引导" width="100"><template #default="{row}">{{row.onboarding_completed?'已完成':'未完成'}}</template></el-table-column>
      <el-table-column prop="last_login" label="最近登录" min-width="170" />
      <el-table-column label="操作" width="260" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openDetail(row)">详情</el-button><el-button v-if="row.status===1" link type="danger" @click="accountAction(row,'suspend','停用账号')">停用</el-button><el-button v-else link type="success" @click="accountAction(row,'reactivate','恢复账号')">恢复</el-button><el-button link @click="accountAction(row,'revoke-sessions','撤销会话')">退出全部设备</el-button></template></el-table-column>
    </el-table></div>

    <section v-if="staffAuth.has('privacy.manage')" class="section-block"><h2>隐私请求</h2><div class="data-surface"><el-table :data="privacyRows"><el-table-column prop="user_email" label="候选人" min-width="220" /><el-table-column prop="request_type" label="类型" width="100" /><el-table-column prop="status" label="状态" width="100" /><el-table-column prop="reason" label="用户说明" min-width="220" show-overflow-tooltip /><el-table-column label="操作" width="150"><template #default="{row}"><template v-if="row.status==='pending'"><el-button link type="primary" @click="decidePrivacy(row,'complete')">完成</el-button><el-button link type="danger" @click="decidePrivacy(row,'reject')">拒绝</el-button></template></template></el-table-column></el-table></div></section>

    <el-drawer v-model="drawer" title="候选人账号详情" size="620px">
      <template v-if="detail"><el-descriptions :column="2" border><el-descriptions-item label="邮箱">{{detail.email}}</el-descriptions-item><el-descriptions-item label="状态">{{detail.status===1?'正常':'停用'}}</el-descriptions-item><el-descriptions-item label="简历">{{detail.counts.resumes}}</el-descriptions-item><el-descriptions-item label="面试">{{detail.counts.interviews}}</el-descriptions-item><el-descriptions-item label="求职目标">{{detail.counts.job_targets}}</el-descriptions-item><el-descriptions-item label="投递记录">{{detail.counts.applications}}</el-descriptions-item><el-descriptions-item label="活动会话">{{detail.counts.active_sessions}}</el-descriptions-item><el-descriptions-item label="隐私请求">{{detail.counts.privacy_requests}}</el-descriptions-item></el-descriptions>
      <el-alert class="private-alert" title="私密业务内容默认受保护" description="访问候选人简历、面试回答或音视频前，必须重新验证 MFA、填写原因并获得 15 分钟只读授权。" type="warning" :closable="false" />
      <el-button v-if="staffAuth.has('candidate.private_access')" type="warning" @click="privateAccessDialog=true">申请严格授权</el-button>
      <h3>近期登录审计</h3><el-table :data="detail.recent_logins"><el-table-column prop="event" label="事件" /><el-table-column prop="success" label="结果"><template #default="{row}">{{row.success?'成功':'失败'}}</template></el-table-column><el-table-column prop="reason" label="原因" /><el-table-column prop="created_at" label="时间" min-width="170" /></el-table></template>
    </el-drawer>
    <el-dialog v-model="privateAccessDialog" title="申请候选人私密数据限时授权" width="520px"><el-alert title="授权只读、15 分钟自动过期，且禁止下载和传播" type="warning" :closable="false" /><el-form label-position="top" style="margin-top:16px"><el-form-item label="访问原因（至少 10 个字）"><el-input v-model="breakGlass.operation_reason" type="textarea" /></el-form-item><el-form-item label="MFA 二次验证"><el-input v-model="breakGlass.mfa_code" maxlength="20" /></el-form-item></el-form><template #footer><el-button @click="privateAccessDialog=false">取消</el-button><el-button type="warning" :disabled="breakGlass.operation_reason.trim().length<10||!breakGlass.mfa_code" @click="grantPrivateAccess">确认授权</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.section-block{margin-top:28px}.section-block h2{font-size:18px}.private-alert{margin:20px 0}h3{margin-top:28px}
</style>
