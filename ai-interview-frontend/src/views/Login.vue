<template>
  <div class="auth-container">
    <div v-if="isAuthenticating" class="auth-loading">
      <el-icon class="is-loading" :size="50"><Loading /></el-icon>
      <p>正在通过 GitHub 授权登录，请稍候...</p>
    </div>
    <el-card class="auth-card" v-show="!isAuthenticating">
      <template #header>
        <div class="card-header">
          <h2>AI 模拟面试平台 - 登录</h2>
        </div>
      </template>
      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-width="80px" @keyup.enter="handleLogin">
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="loginForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" show-password placeholder="请输入密码" />
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
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';
import { useRoute, useRouter } from 'vue-router';
import { Loading } from '@element-plus/icons-vue';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const loading = ref(false);
const isAuthenticating = ref(false);
const loginFormRef = ref<FormInstance>();
const loginForm = reactive({ email: '', password: '' });

// 【核心修正】只定义一次
const loginRules = reactive<FormRules>({
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
});

onMounted(async () => {
  const code = route.query.code as string;
  if (code) {
    isAuthenticating.value = true;
    try {
      await authStore.loginWithGitHub({ code });
      ElMessage.success('GitHub 授权登录成功！');
    } catch (error) {
      console.error('GitHub 登录流程失败', error);
      ElMessage.error('GitHub 授权失败，请重试。');
      await router.replace({ query: {} });
      isAuthenticating.value = false;
    }
  }
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
      } catch (error) { console.error("登录失败", error); } 
      finally { loading.value = false; }
    }
  });
};

const handleGitHubLogin = () => {
  const clientID = import.meta.env.VITE_GITHUB_CLIENT_ID;
  if (!clientID) {
    ElMessage.error('GitHub 登录未配置，请联系管理员。');
    return;
  }
  const redirectUri = "http://localhost:5173/login";
  const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${clientID}&redirect_uri=${redirectUri}&scope=user:email`;
  window.location.href = githubAuthUrl;
};
</script>

<style scoped>
.auth-loading { display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; gap: 20px; color: #606266; }
.third-party-login { margin-top: 20px; }
.icon-group { display: flex; justify-content: center; margin-top: 10px; }
.third-party-icon { width: 32px; height: 32px; cursor: pointer; transition: opacity 0.2s; }
.third-party-icon:hover { opacity: 0.8; }
</style>