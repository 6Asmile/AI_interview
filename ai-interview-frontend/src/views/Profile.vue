<template>
  <div class="profile-page" v-loading="loading">
    <header class="page-header"><div><h1>个人中心</h1><p>管理职业画像、通知、安全会话与隐私数据。</p></div></header>
    <el-tabs v-model="activeTab" class="profile-tabs">
      <el-tab-pane label="职业画像" name="profile">
        <section class="profile-section">
          <div class="avatar-column">
            <el-avatar :size="112" :src="profileForm.avatar || defaultAvatar" />
            <el-upload :show-file-list="false" :before-upload="beforeAvatarUpload" :http-request="handleAvatarUpload"><el-button :icon="Upload">更换头像</el-button></el-upload>
          </div>
          <el-form :model="profileForm" label-width="100px" class="profile-form">
            <el-form-item label="用户名"><el-input v-model="profileForm.username" /></el-form-item>
            <el-form-item label="职业标题"><el-input v-model="profileForm.headline" placeholder="例如：AI 应用开发工程师" /></el-form-item>
            <el-form-item label="所在地区"><el-input v-model="profileForm.location" /></el-form-item>
            <el-form-item label="工作年限"><el-input-number v-model="profileForm.years_experience" :min="0" :max="60" /></el-form-item>
            <el-form-item label="目标岗位"><el-select v-model="profileForm.target_roles" multiple filterable allow-create default-first-option /></el-form-item>
            <el-form-item label="技能画像"><el-select v-model="profileForm.skills_profile" multiple filterable allow-create default-first-option /></el-form-item>
            <el-form-item label="求职状态"><el-input v-model="profileForm.availability" placeholder="在看机会、一个月内到岗等" /></el-form-item>
            <el-form-item label="资料可见"><el-segmented v-model="profileForm.profile_visibility" :options="visibilityOptions" /></el-form-item>
            <el-form-item><el-button type="primary" :loading="savingProfile" @click="saveProfile">保存职业画像</el-button></el-form-item>
          </el-form>
        </section>
      </el-tab-pane>

      <el-tab-pane label="通知偏好" name="notifications">
        <section class="settings-list">
          <label v-for="item in notificationToggles" :key="item.key"><span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span><el-switch v-model="notificationForm[item.key]" /></label>
          <label><span><strong>汇总频率</strong><small>控制非紧急消息的邮件汇总</small></span><el-select v-model="notificationForm.digest_frequency" style="width: 140px"><el-option label="不汇总" value="none" /><el-option label="每日" value="daily" /><el-option label="每周" value="weekly" /></el-select></label>
          <el-button type="primary" @click="saveNotifications">保存通知设置</el-button>
        </section>
      </el-tab-pane>

      <el-tab-pane label="账号安全" name="security">
        <section class="security-grid">
          <div class="security-panel">
            <header><div><h2>双重验证</h2><p>登录时额外验证动态口令或恢复码。</p></div><el-tag :type="mfaStatus.enabled ? 'success' : profileForm.mfa_required ? 'warning' : 'info'">{{ mfaStatus.enabled ? '已启用' : profileForm.mfa_required ? '建议立即启用' : '未启用' }}</el-tag></header>
            <el-button v-if="!mfaStatus.enabled" type="primary" :icon="Lock" @click="beginMFA">配置验证器</el-button>
            <el-button v-else type="danger" plain @click="disableDialog=true">停用双重验证</el-button>
          </div>
          <div class="security-panel">
            <h2>{{ profileForm.has_password ? '修改密码' : '设置密码' }}</h2>
            <el-form ref="passwordFormRef" :model="passwordForm" label-position="top">
              <el-form-item v-if="profileForm.has_password" label="当前密码"><el-input v-model="passwordForm.old_password" type="password" show-password /></el-form-item>
              <el-form-item label="新密码"><el-input v-model="passwordForm.new_password1" type="password" show-password /></el-form-item>
              <el-form-item label="确认新密码"><el-input v-model="passwordForm.new_password2" type="password" show-password /></el-form-item>
              <el-button type="primary" @click="changePassword">更新密码</el-button>
            </el-form>
          </div>
        </section>
        <section class="session-section">
          <header><div><h2>活动会话</h2><p>发现陌生设备时立即撤销，或退出所有设备。</p></div><el-button type="danger" plain @click="logoutAll">退出所有设备</el-button></header>
          <el-table :data="sessions" empty-text="暂无活动会话">
            <el-table-column prop="device_name" label="设备" min-width="130" /><el-table-column prop="ip_address" label="IP" width="140" /><el-table-column prop="last_seen_at" label="最近活动" width="180"><template #default="{row}">{{ formatDateTime(row.last_seen_at) }}</template></el-table-column><el-table-column prop="expires_at" label="到期" width="180"><template #default="{row}">{{ formatDateTime(row.expires_at) }}</template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="danger" @click="revokeSession(row.id)">撤销</el-button></template></el-table-column>
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="账户与隐私" name="privacy">
        <section class="settings-list">
          <label><span><strong>GitHub</strong><small>{{ githubAccount ? `已绑定 ${githubAccount.extra_data.login || githubAccount.uid}` : '未绑定' }}</small></span><el-button v-if="githubAccount" type="danger" plain @click="disconnectGitHub">解绑</el-button><el-button v-else type="primary" @click="connectGitHub">绑定</el-button></label>
          <label><span><strong>导出个人数据</strong><small>导出职业事实、简历当前版本、投递和面试记录，不包含模型密钥。</small></span><el-button @click="exportData">生成导出</el-button></label>
          <label><span><strong>申请注销账号</strong><small>提交后进入人工审核，避免误删求职与面试记录。</small></span><el-button type="danger" plain @click="requestDeletion">申请注销</el-button></label>
        </section>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="mfaDialog" title="配置双重验证" width="480px">
      <div class="mfa-setup"><img v-if="mfaSetup.qr_code" :src="mfaSetup.qr_code" alt="TOTP QR Code" /><p>使用验证器扫描二维码，再输入当前 6 位动态口令。</p><el-input v-model="mfaCode" maxlength="8" placeholder="动态口令" /></div>
      <template #footer><el-button @click="mfaDialog=false">取消</el-button><el-button type="primary" @click="verifyMFA">确认启用</el-button></template>
    </el-dialog>
    <el-dialog v-model="recoveryDialog" title="保存恢复码" width="520px"><el-alert title="每个恢复码只能使用一次。关闭后系统不会再次显示完整恢复码。" type="warning" :closable="false" /><pre class="recovery-codes">{{ recoveryCodes.join('\n') }}</pre><template #footer><el-button type="primary" @click="recoveryDialog=false">我已妥善保存</el-button></template></el-dialog>
    <el-dialog v-model="disableDialog" title="停用双重验证" width="460px"><el-form label-position="top"><el-form-item label="当前密码"><el-input v-model="disableForm.password" type="password" show-password /></el-form-item><el-form-item label="动态口令"><el-input v-model="disableForm.code" /></el-form-item></el-form><template #footer><el-button @click="disableDialog=false">取消</el-button><el-button type="danger" @click="disableMFA">确认停用</el-button></template></el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, UploadProps, UploadRequestOptions } from 'element-plus';
import { Lock, Upload } from '@element-plus/icons-vue';
import { useAuthStore } from '@/store/modules/auth';
import {
  changePasswordApi, createPrivacyRequestApi, disableMFAApi, disconnectSocialApi,
  getAuthSessionsApi, getMFAStatusApi, getNotificationPreferenceApi, getUserProfileApi,
  logoutAllSessionsApi, revokeAuthSessionApi, setupMFAApi, updateNotificationPreferenceApi,
  updateUserProfileApi, uploadAvatarApi, verifyMFAApi,
  type AuthSession, type ChangePasswordData, type NotificationPreference, type SocialAccount, type UserProfile,
} from '@/api/modules/user';
import defaultAvatar from '@/assets/images/default_avatar.png';
import { formatDateTime } from '@/utils/format';

const authStore = useAuthStore();
const activeTab = ref('profile'); const loading = ref(true); const savingProfile = ref(false);
const profileForm = reactive<Partial<UserProfile>>({ target_roles: [], skills_profile: [], profile_visibility: 'private' });
const notificationForm = reactive<any>({}); const sessions = ref<AuthSession[]>([]); const mfaStatus = reactive<any>({ enabled: false });
const passwordFormRef = ref<FormInstance>(); const passwordForm = reactive<ChangePasswordData>({ old_password: '', new_password1: '', new_password2: '' });
const mfaDialog = ref(false); const recoveryDialog = ref(false); const disableDialog = ref(false); const mfaSetup = reactive<any>({}); const mfaCode = ref(''); const recoveryCodes = ref<string[]>([]); const disableForm = reactive({ password: '', code: '' });
const visibilityOptions = [{ label: '仅自己', value: 'private' }, { label: '社区可见', value: 'community' }, { label: '公开', value: 'public' }];
const notificationToggles = [
  { key: 'in_app_enabled', label: '站内通知', description: '面试、投递和系统消息' }, { key: 'email_enabled', label: '邮件通知', description: '重要事项发送到登录邮箱' },
  { key: 'interview_reminders', label: '面试提醒', description: '面试计划和复盘任务' }, { key: 'application_updates', label: '投递提醒', description: '下一步动作和状态更新' },
  { key: 'community_updates', label: '社区动态', description: '关注主题和文章互动' }, { key: 'direct_messages', label: '私信提醒', description: '求职与面试私密沟通' },
];
const githubAccount = computed<SocialAccount | undefined>(() => profileForm.socialaccount_set?.find(item => item.provider === 'github'));

async function load() { loading.value = true; try { const [profile, pref, sessionList, mfa] = await Promise.all([getUserProfileApi(), getNotificationPreferenceApi(), getAuthSessionsApi(), getMFAStatusApi()]); Object.assign(profileForm, profile); Object.assign(notificationForm, pref); sessions.value = sessionList; Object.assign(mfaStatus, mfa); } finally { loading.value = false; } }
onMounted(load);
const beforeAvatarUpload: UploadProps['beforeUpload'] = file => { const valid = ['image/jpeg','image/png','image/webp'].includes(file.type) && file.size < 2 * 1024 * 1024; if (!valid) ElMessage.error('头像需为 JPG/PNG/WebP 且不超过 2MB'); return valid; };
async function handleAvatarUpload(options: UploadRequestOptions) { const data = new FormData(); data.append('avatar', options.file); const result = await uploadAvatarApi(data); profileForm.avatar = result.avatar_url; await authStore.fetchUser(); }
async function saveProfile() { savingProfile.value = true; try { await updateUserProfileApi(profileForm); await authStore.fetchUser(); ElMessage.success('职业画像已保存'); } finally { savingProfile.value = false; } }
async function saveNotifications() { await updateNotificationPreferenceApi(notificationForm); ElMessage.success('通知设置已保存'); }
async function changePassword() { if (passwordForm.new_password1 !== passwordForm.new_password2) return ElMessage.warning('两次密码不一致'); await changePasswordApi(passwordForm); Object.assign(passwordForm, { old_password: '', new_password1: '', new_password2: '' }); ElMessage.success('密码已更新'); }
async function beginMFA() { Object.assign(mfaSetup, await setupMFAApi()); mfaCode.value = ''; mfaDialog.value = true; }
async function verifyMFA() { const result: any = await verifyMFAApi(mfaCode.value); recoveryCodes.value = result.recovery_codes || []; mfaDialog.value = false; recoveryDialog.value = true; await load(); }
async function disableMFA() { await disableMFAApi(disableForm.password, disableForm.code); disableDialog.value = false; Object.assign(disableForm, { password: '', code: '' }); await load(); }
async function revokeSession(id: string) { await revokeAuthSessionApi(id); sessions.value = sessions.value.filter(item => item.id !== id); }
async function logoutAll() { await ElMessageBox.confirm('这会让所有设备上的登录失效，是否继续？', '退出所有设备'); await logoutAllSessionsApi(); authStore.logout(); }
function connectGitHub() { const clientID = import.meta.env.VITE_GITHUB_CLIENT_ID; if (!clientID) return ElMessage.error('GitHub 登录未配置'); localStorage.setItem('oauth_flow', 'connect'); window.location.href = `https://github.com/login/oauth/authorize?client_id=${clientID}&redirect_uri=${encodeURIComponent(`${window.location.origin}/oauth/callback`)}&scope=user:email`; }
async function disconnectGitHub() { if (!githubAccount.value) return; await ElMessageBox.confirm('确认解绑 GitHub？', '账户解绑'); await disconnectSocialApi(githubAccount.value.id); await load(); }
async function exportData() { const result: any = await createPrivacyRequestApi('export'); const blob = new Blob([JSON.stringify(result.result, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `ifaceoff-data-${new Date().toISOString().slice(0,10)}.json`; link.click(); URL.revokeObjectURL(url); }
async function requestDeletion() { const { value } = await ElMessageBox.prompt('请说明注销原因，提交后由管理员审核。', '申请注销', { inputType: 'textarea' }); await createPrivacyRequestApi('delete', value); ElMessage.success('注销申请已提交'); }
</script>

<style scoped>
.profile-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }
.page-header { padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }
.page-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; } .page-header p { margin: 8px 0 0; color: #667085; }
.profile-tabs { margin-top: 18px; padding: 0 20px 24px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }
.profile-section { display: grid; grid-template-columns: 150px minmax(0, 620px); gap: 30px; padding-top: 12px; }
.avatar-column { display: flex; flex-direction: column; align-items: center; gap: 14px; }.profile-form { width: 100%; }
.settings-list { max-width: 780px; padding-top: 8px; }.settings-list > label { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 16px 0; border-bottom: 1px solid #edf0f4; }.settings-list strong,.settings-list small { display: block; }.settings-list small { margin-top: 4px; color: #667085; }
.security-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }.security-panel,.session-section { padding: 18px; border: 1px solid #e1e6ee; border-radius: 6px; }.security-panel > header,.session-section > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.security-panel h2,.session-section h2 { margin: 0; font-size: 18px; }.security-panel p,.session-section p { margin: 6px 0 16px; color: #667085; }.session-section { margin-top: 18px; }
.mfa-setup { text-align: center; }.mfa-setup img { width: 220px; height: 220px; }.mfa-setup p { color: #667085; }.recovery-codes { padding: 16px; background: #f5f7fa; font-size: 16px; line-height: 1.8; columns: 2; }
@media (max-width: 760px) { .profile-page { padding: 14px; }.profile-section,.security-grid { grid-template-columns: 1fr; }.avatar-column { align-items: flex-start; }.settings-list > label { align-items: flex-start; flex-direction: column; } }
</style>
