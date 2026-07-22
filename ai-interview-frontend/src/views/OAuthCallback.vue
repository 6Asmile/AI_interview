<template>
  <main class="callback-page">
    <section class="callback-panel">
      <template v-if="linkRequired">
        <h1>确认绑定已有账号</h1>
        <p>GitHub 验证邮箱 {{ emailHint }} 已存在。请输入原账号密码，确认由你本人完成绑定。</p>
        <el-form label-position="top" @submit.prevent="confirmLink">
          <el-form-item label="原账号密码">
            <el-input v-model="password" type="password" show-password autocomplete="current-password" />
          </el-form-item>
          <el-button type="primary" :loading="loading" :disabled="!password" @click="confirmLink">确认并登录</el-button>
          <el-button @click="router.replace('/login')">取消</el-button>
        </el-form>
      </template>
      <template v-else>
        <el-icon v-if="loading" class="is-loading" :size="44"><Loading /></el-icon>
        <el-icon v-else class="error-icon" :size="44"><WarningFilled /></el-icon>
        <h1>{{ loading ? '正在完成 GitHub 授权' : 'GitHub 授权未完成' }}</h1>
        <p>{{ message }}</p>
        <el-button v-if="!loading" type="primary" @click="router.replace('/login')">返回登录</el-button>
      </template>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Loading, WarningFilled } from '@element-plus/icons-vue';
import { browserSessionApi, confirmGitHubLinkApi, ensureCsrfApi } from '@/api/modules/auth';
import { useAuthStore } from '@/store/modules/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const loading = ref(true);
const linkRequired = ref(false);
const password = ref('');
const emailHint = ref(String(route.query.email_hint || ''));
const message = ref('正在安全地建立候选人会话，请稍候。');
const linkToken = String(route.query.link_token || '');

const errorMessages: Record<string, string> = {
  oauth_cancelled: '你取消了 GitHub 授权。',
  oauth_state_missing: '授权状态缺失，请重新发起登录。',
  oauth_state_invalid: '授权状态已过期或已经使用，请重新发起登录。',
  github_provider_unavailable: '暂时无法连接 GitHub，请稍后重试。',
  github_token_exchange_failed: 'GitHub 授权码交换失败，请重新授权。',
  github_verified_email_required: 'GitHub 没有提供已验证邮箱，请先在 GitHub 中验证邮箱。',
  github_identity_in_use: '该 GitHub 身份已经绑定其他账号。',
  candidate_disabled: '该候选人账号已被停用。',
};

const completeLogin = async () => {
  await ensureCsrfApi();
  const session = await browserSessionApi();
  authStore.setSession(session.access, session.user);
  authStore.initialized = true;
  const next = String(route.query.next || (session.user.onboarding_completed_at ? '/dashboard' : '/onboarding'));
  await router.replace(next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard');
};

const confirmLink = async () => {
  loading.value = true;
  try {
    await ensureCsrfApi();
    const result = await confirmGitHubLinkApi(linkToken, password.value);
    await authStore.handleLoginSuccess(result.access);
    ElMessage.success('GitHub 已安全绑定到原账号。');
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || '账号绑定确认失败。');
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  const status = String(route.query.status || '');
  if (status === 'link_required' && linkToken) {
    linkRequired.value = true;
    loading.value = false;
    return;
  }
  if (status === 'success') {
    if (route.query.flow === 'connect') {
      ElMessage.success('GitHub 账号绑定成功。');
      await router.replace(String(route.query.next || '/dashboard/profile'));
      return;
    }
    try {
      await completeLogin();
      ElMessage.success('GitHub 登录成功。');
      return;
    } catch {
      message.value = '授权已完成，但会话建立失败，请返回登录页重试。';
    }
  } else {
    const code = String(route.query.code || 'oauth_state_invalid');
    message.value = errorMessages[code] || 'GitHub 授权失败，请重新发起登录。';
  }
  loading.value = false;
});
</script>

<style scoped>
.callback-page { min-height: 100vh; display: grid; place-items: center; padding: 32px; background: #f4f7fb; }
.callback-panel { width: min(480px, 100%); padding: 32px; border: 1px solid #dce4ef; border-radius: 8px; background: #fff; text-align: center; }
.callback-panel h1 { margin: 16px 0 8px; font-size: 24px; }
.callback-panel p { margin: 0 0 24px; color: #667085; line-height: 1.7; }
.callback-panel .el-form { text-align: left; }
.error-icon { color: #d97706; }
</style>
