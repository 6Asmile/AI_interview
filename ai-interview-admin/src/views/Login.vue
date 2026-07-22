<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { staffAuth } from '@/auth';

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const form = reactive({ email: '', password: '', mfa_code: '' });
const candidateLoginUrl = import.meta.env.VITE_CANDIDATE_APP_URL || 'http://127.0.0.1:5173/login';
const submit = async () => {
  loading.value = true;
  try {
    await staffAuth.login(form);
    await router.replace(String(route.query.redirect || '/'));
  } catch (error: any) {
    const data = error?.response?.data;
    if (error?.response?.status === 409 && data?.challenge_token) {
      sessionStorage.setItem('staff_security_challenge', data.challenge_token);
      await router.push('/security-setup');
    } else if (data?.code === 'staff_mfa_required') {
      ElMessage.warning('请输入验证器中的 6 位动态口令。');
    } else {
      ElMessage.error(data?.message || '员工账号登录失败。');
    }
  } finally { loading.value = false; }
};
</script>

<template>
  <main class="login-page">
    <section class="login-context">
      <span class="brand-mark">IF</span><p>iFaceoff Staff Console</p>
      <h1>员工管理与运行审计</h1>
      <ul><li>独立员工账号与候选人身份完全隔离</li><li>知识审批、Agent Trace 和模型健康统一审计</li><li>敏感操作要求 MFA、原因和幂等键</li></ul>
    </section>
    <section class="login-form" aria-labelledby="login-title">
      <h2 id="login-title">员工登录</h2><p>候选人账号无法登录此管理端。</p>
      <el-form label-position="top" @keyup.enter="submit">
        <el-form-item label="员工邮箱"><el-input v-model="form.email" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" /></el-form-item>
        <el-form-item label="MFA 动态口令或恢复码"><el-input v-model="form.mfa_code" maxlength="20" autocomplete="one-time-code" placeholder="首次登录可暂不填写" /></el-form-item>
        <el-button type="primary" :loading="loading" class="submit" @click="submit">登录员工端</el-button>
      </el-form>
      <div class="login-links"><router-link to="/register">使用邀请注册员工账号</router-link><a :href="candidateLoginUrl">返回求职者登录</a></div>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(420px, 1fr) 480px; background: #f3f5f7; }
.login-context { display: grid; align-content: center; padding: 8vw; color: #eaf0ff; background: #17366f; }
.brand-mark { display: grid; width: 42px; height: 42px; place-content: center; color: #17366f; background: #fff; font-weight: 800; }
.login-context p { margin: 20px 0 8px; color: #bfcdf0; }
.login-context h1 { margin: 0 0 30px; font-size: 38px; letter-spacing: 0; }
.login-context ul { margin: 0; padding-left: 20px; line-height: 2.2; }
.login-form { align-self: center; margin: 40px; padding: 38px; border: 1px solid #d9dee5; border-radius: 6px; background: #fff; }
.login-form h2 { margin: 0; font-size: 28px; }
.login-form > p { margin: 8px 0 26px; color: #667085; }
.submit { width: 100%; margin-bottom: 20px; }
.login-links { display:flex; justify-content:space-between; gap:16px; }.login-form a { color: #1d4ed8; font-size: 13px; text-decoration: none; }
</style>
