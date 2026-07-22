<template>
  <div class="auth-shell">
    <div v-if="isAuthenticating" class="auth-loading">
      <el-icon class="is-loading" :size="50"><Loading /></el-icon>
      <p>正在通过 GitHub 授权登录，请稍候...</p>
    </div>
    <div class="auth-layout" v-show="!isAuthenticating">
      <section class="auth-visual">
        <p class="auth-eyebrow">IFaceOff</p>
        <h1>进入你的 AI 模拟面试训练空间</h1>
        <p>围绕岗位、JD 和简历动态追问，沉淀可复盘的回答质量与能力验证链路。</p>
        <img src="/hero.webp" alt="AI 模拟面试平台" />
      </section>
      <el-card class="auth-card">
      <div class="card-header">
        <p class="auth-eyebrow">Welcome Back</p>
        <h2>登录账号</h2>
        <span>继续你的面试训练、简历诊断和复盘报告。</span>
      </div>
      <div class="login-surface-switch">
        <el-button type="primary">求职者登录</el-button>
        <el-button @click="openAdminLogin">管理端登录</el-button>
      </div>
      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-width="80px" @keyup.enter="handleLogin">
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="loginForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item v-if="mfaRequired" label="验证码" prop="mfa_code">
          <el-input v-model="loginForm.mfa_code" maxlength="12" autocomplete="one-time-code" placeholder="动态口令或恢复码" />
        </el-form-item>
        <el-form-item>
          <el-button :loading="loading" @click="handleLogin" class="beautiful-button">登录</el-button>
        </el-form-item>
      </el-form>
      <div class="third-party-login">
        <el-divider>其他登录方式</el-divider>
        <div class="icon-group">
          <img src="@/assets/icons/github.svg" alt="GitHub" @click="handleGitHubLogin" class="third-party-icon" />
        </div>
      </div>
      <div class="auth-footer">
        还没有账号？ <router-link to="/register">立即注册</router-link>
      </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';
import { useRouter } from 'vue-router';
import { Loading } from '@element-plus/icons-vue';
import { startGitHubOAuthApi } from '@/api/modules/auth';

const authStore = useAuthStore();
const router = useRouter();

const loading = ref(false);
const isAuthenticating = ref(false);
const loginFormRef = ref<FormInstance>();
const loginForm = reactive({ email: '', password: '', mfa_code: '' });
const mfaRequired = ref(false);

// 【核心修正】只定义一次
const loginRules = reactive<FormRules>({
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
});

// 【核心修正】只定义一次
const handleLogin = async () => {
  if (!loginFormRef.value) return;
  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true;
      try {
        await authStore.loginWithCredentials(loginForm);
        ElMessage.success('登录成功！');
      } catch (error: any) {
        if (error?.response?.data?.mfa_required || error?.response?.data?.mfa_code) {
          mfaRequired.value = true;
          ElMessage.info('请输入验证器动态口令或恢复码后再次登录。');
        }
        console.error("登录失败", error);
      }
      finally { loading.value = false; }
    }
  });
};

const handleGitHubLogin = async () => {
  isAuthenticating.value = true;
  try {
    const result = await startGitHubOAuthApi('login', '/dashboard');
    window.location.assign(result.authorize_url);
  } catch (error: any) {
    isAuthenticating.value = false;
    ElMessage.error(error?.response?.data?.message || 'GitHub 登录暂不可用，请稍后重试。');
  }
};

const openAdminLogin = () => {
  window.location.href = import.meta.env.VITE_ADMIN_APP_URL || 'http://127.0.0.1:5174/login';
};
</script>

<style scoped>
.auth-shell {
  min-height: 100vh;
  padding: 32px;
  background:
    radial-gradient(circle at 12% 10%, rgba(86, 151, 255, 0.18), transparent 30%),
    radial-gradient(circle at 88% 14%, rgba(40, 204, 171, 0.13), transparent 26%),
    linear-gradient(180deg, #f6f9ff 0%, #edf3fb 100%);
}

.auth-loading {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: calc(100vh - 64px);
  gap: 20px;
  color: #606266;
}

.auth-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(390px, 0.72fr);
  gap: 28px;
  width: min(1180px, 100%);
  min-height: calc(100vh - 64px);
  margin: 0 auto;
  align-items: center;
}

.auth-visual,
.auth-card {
  border: 1px solid rgba(201, 214, 236, 0.85);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 24px 60px rgba(47, 74, 119, 0.1);
  overflow: hidden;
}

.auth-visual {
  padding: 34px;
}

.auth-eyebrow {
  margin: 0 0 10px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.auth-visual h1 {
  max-width: 620px;
  margin: 0;
  color: #1c2d4b;
  font-size: clamp(34px, 3.5vw, 54px);
  line-height: 1.15;
}

.auth-visual p:not(.auth-eyebrow) {
  max-width: 600px;
  margin: 18px 0 26px;
  color: #60708f;
  line-height: 1.8;
}

.auth-visual img {
  display: block;
  width: 100%;
  max-height: 390px;
  object-fit: cover;
  border-radius: 24px;
  border: 1px solid #dbe7f8;
}

.auth-card {
  padding: 8px;
}

.auth-card :deep(.el-card__header) {
  display: none;
}

.auth-card :deep(.el-card__body) {
  padding: 30px;
}

.card-header {
  margin-bottom: 24px;
}

.login-surface-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 22px;
}

.login-surface-switch .el-button { margin: 0; }

.card-header h2 {
  margin: 0 0 8px;
  color: #1d3150;
  font-size: 30px;
}

.card-header span {
  color: #6a7a94;
}

.auth-card :deep(.el-input__wrapper) {
  min-height: 44px;
  border-radius: 14px;
  box-shadow: 0 0 0 1px #dfe8f6 inset;
}

.beautiful-button {
  width: 100%;
  min-height: 46px;
  border: none;
  border-radius: 15px;
  color: #fff;
  background: linear-gradient(135deg, #255fd2 0%, #66a2ff 100%);
}

.third-party-login {
  margin-top: 20px;
}

.icon-group {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.third-party-icon {
  width: 34px;
  height: 34px;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.2s;
}

.third-party-icon:hover {
  opacity: 0.85;
  transform: translateY(-1px);
}

.auth-footer {
  margin-top: 20px;
  text-align: center;
  color: #667792;
}

.auth-footer a {
  color: #2869d8;
  font-weight: 700;
  text-decoration: none;
}

@media (max-width: 920px) {
  .auth-layout {
    grid-template-columns: 1fr;
  }

  .auth-visual {
    display: none;
  }
}
</style>
