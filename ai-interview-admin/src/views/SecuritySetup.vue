<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { api, getCsrf } from '@/api';
import { staffAuth } from '@/auth';

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const challenge = ref(sessionStorage.getItem('staff_security_challenge') || '');
const secret = ref('');
const uri = ref('');
const invitation = ref<any>(null);
const recoveryCodes = ref<string[]>([]);
const recoveryConfirmed = ref(false);
const recoveryConfirmationToken = ref('');
const manualInvite = ref('');
const invitationError = ref('');
const inviteToken = computed(() => String(route.query.invite || route.query.token || ''));
const activation = reactive({ display_name: '', password: '', password_confirm: '' });
const form = reactive({ code: '', new_password: '' });

const loadSecret = async () => {
  const result = await api.post('/auth/security-setup/', { challenge_token: challenge.value });
  secret.value = result.secret || '';
  uri.value = result.otpauth_uri || '';
};

const loadInvitation = async () => {
  if (!inviteToken.value || challenge.value) return;
  try {
    invitationError.value = '';
    invitation.value = await api.get(`/auth/invitations/${encodeURIComponent(inviteToken.value)}/`);
    activation.display_name = invitation.value.display_name || '';
  } catch (error: any) {
    invitationError.value = error?.response?.data?.message || '邀请无效或已过期。';
    ElMessage.error(invitationError.value);
  }
};

const openManualInvitation = async () => {
  const token = manualInvite.value.trim();
  if (!token) return;
  await router.replace({ path: '/register', query: { invite: token } });
  await loadInvitation();
};

const activate = async () => {
  if (!invitation.value) return;
  if (activation.password !== activation.password_confirm) {
    ElMessage.warning('两次输入的密码不一致。');
    return;
  }
  loading.value = true;
  try {
    await getCsrf();
    const result = await api.post('/auth/register/', {
      invite: inviteToken.value,
      display_name: activation.display_name,
      password: activation.password,
    });
    challenge.value = result.challenge_token;
    sessionStorage.setItem('staff_security_challenge', challenge.value);
    await loadSecret();
  } catch (error: any) {
    const fields = error?.response?.data?.field_errors?.password;
    ElMessage.error(fields?.join('；') || error?.response?.data?.message || '邀请注册失败。');
  } finally {
    loading.value = false;
  }
};

const confirm = async () => {
  loading.value = true;
  try {
    const result = await api.post('/auth/security-setup/', {
      challenge_token: challenge.value,
      code: form.code,
      new_password: form.new_password,
    });
    recoveryCodes.value = result.recovery_codes || [];
    recoveryConfirmationToken.value = result.recovery_confirmation_token || '';
    if (!recoveryCodes.value.length) {
      staffAuth.state.account = result.account;
      staffAuth.state.initialized = true;
      sessionStorage.removeItem('staff_security_challenge');
      await router.replace('/');
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || '安全设置未完成。');
  } finally {
    loading.value = false;
  }
};

const finish = async () => {
  if (!recoveryConfirmed.value) return;
  loading.value = true;
  try {
    const result = await api.post('/auth/security-setup/', {
      recovery_confirmation_token: recoveryConfirmationToken.value,
      recovery_codes_confirmed: true,
    });
    staffAuth.state.account = result.account;
    staffAuth.state.initialized = true;
    sessionStorage.removeItem('staff_security_challenge');
    recoveryCodes.value = [];
    recoveryConfirmationToken.value = '';
    await router.replace('/');
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || '恢复码确认失败，请重新登录。');
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  await getCsrf();
  if (challenge.value) await loadSecret();
  else await loadInvitation();
});
</script>

<template>
  <main class="setup-page">
    <section class="setup-panel">
      <template v-if="recoveryCodes.length">
        <p class="eyebrow">最后一步</p>
        <h1>保存员工恢复码</h1>
        <p>每个恢复码只能使用一次，关闭页面后不会再次显示完整内容。</p>
        <pre class="recovery-codes">{{ recoveryCodes.join('\n') }}</pre>
        <el-checkbox v-model="recoveryConfirmed">我已将恢复码保存到安全位置</el-checkbox>
        <el-button class="primary-action" type="primary" :loading="loading" :disabled="!recoveryConfirmed" @click="finish">确认并进入运营后台</el-button>
      </template>
      <template v-else-if="!challenge">
        <p class="eyebrow">仅限受邀员工</p>
        <h1>注册员工账号</h1>
        <p>员工身份与求职者账号完全隔离，注册后必须绑定 MFA。</p>
        <el-form v-if="!inviteToken" label-position="top" @submit.prevent="openManualInvitation">
          <el-form-item label="邀请令牌"><el-input v-model="manualInvite" placeholder="粘贴管理员发送的一次性邀请令牌" /></el-form-item>
          <el-button class="primary-action" type="primary" :disabled="!manualInvite.trim()" @click="openManualInvitation">验证邀请</el-button>
        </el-form>
        <el-result v-else-if="invitationError" icon="warning" title="邀请不可用" :sub-title="invitationError"><template #extra><el-button @click="router.replace('/register')">重新输入</el-button></template></el-result>
        <el-skeleton v-else-if="!invitation" :rows="4" animated />
        <el-form v-else label-position="top" @submit.prevent="activate">
          <el-form-item label="受邀邮箱"><el-input :model-value="invitation.email" disabled /></el-form-item>
          <el-form-item label="员工角色"><el-input :model-value="invitation.roles.join('、')" disabled /></el-form-item>
          <el-form-item label="显示名称"><el-input v-model="activation.display_name" maxlength="120" /></el-form-item>
          <el-form-item label="设置管理端密码"><el-input v-model="activation.password" type="password" show-password autocomplete="new-password" /></el-form-item>
          <el-form-item label="确认密码"><el-input v-model="activation.password_confirm" type="password" show-password autocomplete="new-password" /></el-form-item>
          <el-button class="primary-action" type="primary" :loading="loading" :disabled="!activation.password || !activation.password_confirm" @click="activate">继续配置 MFA</el-button>
        </el-form>
      </template>
      <template v-else>
        <p class="eyebrow">双重验证</p>
        <h1>绑定员工验证器</h1>
        <p>将密钥或 URI 导入支持 TOTP 的验证器，然后输入当前 6 位动态口令。</p>
        <div v-if="secret" class="secret-box">
          <span>验证器密钥</span><strong>{{ secret }}</strong><code>{{ uri }}</code>
        </div>
        <el-alert v-else type="info" :closable="false" title="请输入现有验证器动态口令完成安全确认。" />
        <el-form label-position="top" @submit.prevent="confirm">
          <el-form-item label="6 位动态口令"><el-input v-model="form.code" maxlength="12" inputmode="numeric" autocomplete="one-time-code" /></el-form-item>
          <el-form-item v-if="!secret" label="新密码（要求修改时填写）"><el-input v-model="form.new_password" type="password" show-password /></el-form-item>
          <el-button class="primary-action" type="primary" :loading="loading" :disabled="!form.code" @click="confirm">完成安全设置</el-button>
        </el-form>
      </template>
    </section>
  </main>
</template>

<style scoped>
.setup-page { min-height: 100vh; display: grid; place-items: center; padding: 40px; background: #f3f5f7; }
.setup-panel { width: min(620px, 100%); padding: 36px; border: 1px solid #d9dee5; border-radius: 6px; background: #fff; }
.setup-panel h1 { margin: 0; font-size: 28px; }
.setup-panel > p:not(.eyebrow) { margin: 8px 0 24px; color: #667085; line-height: 1.7; }
.eyebrow { margin: 0 0 8px; color: #1d4ed8; font-size: 12px; font-weight: 800; }
.secret-box { display: grid; gap: 8px; margin-bottom: 22px; padding: 16px; background: #f7f9fc; overflow-wrap: anywhere; }
.secret-box span { color: #667085; }.secret-box strong { font-family: monospace; font-size: 18px; }.secret-box code { color: #475467; font-size: 11px; }
.primary-action { width: 100%; margin-top: 8px; }
.recovery-codes { padding: 18px; border: 1px solid #d9dee5; background: #f7f9fc; font-size: 15px; line-height: 1.8; columns: 2; }
</style>
