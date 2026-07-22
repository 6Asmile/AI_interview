<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';

const loading = ref(false);
const inviteDialog = ref(false);
const editDialog = ref(false);
const accounts = ref<any[]>([]);
const roles = ref<any[]>([]);
const activationUrl = ref('');
const selected = ref<any>(null);
const form = reactive({ email: '', display_name: '', roles: [] as string[], operation_reason: '' });
const editForm = reactive({ display_name: '', roles: [] as string[], status: '', operation_reason: '' });

const load = async () => {
  loading.value = true;
  try {
    const [staffRows, roleRows] = await Promise.all([api.get('/staff/'), api.get('/staff/roles/')]);
    accounts.value = staffRows;
    roles.value = roleRows.results || roleRows;
  } finally { loading.value = false; }
};

const openInvite = () => {
  activationUrl.value = '';
  Object.assign(form, { email: '', display_name: '', roles: [], operation_reason: '' });
  inviteDialog.value = true;
};

const invite = async () => {
  const result = await api.post('/staff-invitations/', form, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  activationUrl.value = result.activation_url;
  ElMessage.success('邀请已进入邮件发送队列，备用链接只在本次显示。');
  await load();
};

const openEdit = (row: any) => {
  selected.value = row;
  Object.assign(editForm, {
    display_name: row.display_name,
    roles: row.roles.map((item: any) => item.slug),
    status: row.status,
    operation_reason: '',
  });
  editDialog.value = true;
};

const saveEdit = async () => {
  await api.patch(`/staff/${selected.value.id}/`, editForm, {
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
  editDialog.value = false;
  ElMessage.success('员工账号已更新。');
  await load();
};

const runAction = async (row: any, action: string, label: string) => {
  const { value } = await ElMessageBox.prompt(`请输入${label}原因`, label, { inputType: 'textarea' });
  const result = await api.post(`/staff/${row.id}/${action}/`, { operation_reason: value }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  ElMessage.success(`${label}已完成。`);
  await load();
  return result;
};

const invitationAction = async (row: any, action: 'resend' | 'revoke') => {
  const { value } = await ElMessageBox.prompt(`请输入${action === 'resend' ? '重新发送' : '撤销'}邀请的原因`, '邀请操作', { inputType: 'textarea' });
  const result = await api.post(`/staff-invitations/${row.invitation.id}/${action}/`, { operation_reason: value }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  if (result.activation_url) {
    activationUrl.value = result.activation_url;
    inviteDialog.value = true;
  }
  ElMessage.success(action === 'resend' ? '新邀请已进入发送队列。' : '邀请已撤销。');
  await load();
};

const copyUrl = async () => {
  await navigator.clipboard.writeText(activationUrl.value);
  ElMessage.success('备用链接已复制。');
};

onMounted(load);
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="page-header">
      <div><h1>员工与权限</h1><p>邀请注册、角色授权、MFA 和活动会话均与候选人身份域隔离。</p></div>
      <el-button type="primary" @click="openInvite">邀请员工</el-button>
    </header>
    <div class="data-surface" style="margin-top:18px">
      <el-table :data="accounts">
        <el-table-column prop="display_name" label="姓名" min-width="130" />
        <el-table-column prop="email" label="邮箱" min-width="220" />
        <el-table-column label="状态" width="110"><template #default="{row}"><el-tag :type="row.status==='active'?'success':row.status==='suspended'?'danger':'warning'">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column label="角色" min-width="200"><template #default="{row}">{{ row.roles.map((item:any)=>item.name).join('、') }}</template></el-table-column>
        <el-table-column label="安全" width="150"><template #default="{row}"><span>{{ row.mfa_enabled?'MFA 已启用':'MFA 未绑定' }}</span><small class="table-note">{{ row.active_sessions }} 个活动会话</small></template></el-table-column>
        <el-table-column label="邀请" width="120"><template #default="{row}">{{ row.invitation?.status || '已激活' }}</template></el-table-column>
        <el-table-column label="操作" width="250" fixed="right"><template #default="{row}">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-dropdown trigger="click">
            <el-button link>安全操作</el-button>
            <template #dropdown><el-dropdown-menu>
              <el-dropdown-item @click="runAction(row,'revoke-sessions','撤销会话')">撤销全部会话</el-dropdown-item>
              <el-dropdown-item @click="runAction(row,'reset-mfa','重置 MFA')">重置 MFA</el-dropdown-item>
              <el-dropdown-item v-if="row.invitation?.status !== 'accepted'" @click="invitationAction(row,'resend')">重新发送邀请</el-dropdown-item>
              <el-dropdown-item v-if="row.invitation?.status === 'pending'" divided @click="invitationAction(row,'revoke')">撤销邀请</el-dropdown-item>
            </el-dropdown-menu></template>
          </el-dropdown>
        </template></el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="inviteDialog" title="邀请独立员工账号" width="560px">
      <el-form label-position="top">
        <template v-if="!activationUrl">
          <el-form-item label="员工邮箱"><el-input v-model="form.email" /></el-form-item>
          <el-form-item label="显示名称"><el-input v-model="form.display_name" /></el-form-item>
          <el-form-item label="角色"><el-select v-model="form.roles" multiple style="width:100%"><el-option v-for="role in roles" :key="role.slug" :label="role.name" :value="role.slug" /></el-select></el-form-item>
          <el-form-item label="操作原因"><el-input v-model="form.operation_reason" type="textarea" /></el-form-item>
        </template>
        <el-alert v-else type="warning" :closable="false" title="一次性备用激活地址">
          <p class="activation-url">{{ activationUrl }}</p><el-button size="small" @click="copyUrl">复制链接</el-button>
        </el-alert>
      </el-form>
      <template #footer><el-button @click="inviteDialog=false">关闭</el-button><el-button v-if="!activationUrl" type="primary" :disabled="!form.email||!form.roles.length||!form.operation_reason.trim()" @click="invite">创建并发送邀请</el-button></template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑员工账号" width="560px">
      <el-form label-position="top">
        <el-form-item label="显示名称"><el-input v-model="editForm.display_name" /></el-form-item>
        <el-form-item label="角色"><el-select v-model="editForm.roles" multiple style="width:100%"><el-option v-for="role in roles" :key="role.slug" :label="role.name" :value="role.slug" /></el-select></el-form-item>
        <el-form-item label="账号状态"><el-radio-group v-model="editForm.status"><el-radio-button value="active">正常</el-radio-button><el-radio-button value="suspended">停用</el-radio-button></el-radio-group></el-form-item>
        <el-form-item label="操作原因"><el-input v-model="editForm.operation_reason" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editDialog=false">取消</el-button><el-button type="primary" :disabled="!editForm.operation_reason.trim()" @click="saveEdit">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.table-note { display:block; color:#667085; font-size:12px; }.activation-url{overflow-wrap:anywhere;line-height:1.6}.el-dropdown{margin-left:12px}
</style>
