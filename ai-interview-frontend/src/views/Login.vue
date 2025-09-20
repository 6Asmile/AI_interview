<template>
  <div class="auth-container">
    <el-card class="auth-card">
      <template #header>
        <div class="card-header">
          <h2>AI 模拟面试平台 - 登录</h2>
        </div>
      </template>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        label-width="80px"
        @keyup.enter="handleLogin"
      >
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="loginForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            show-password
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleLogin"
            class="beautiful-button"
          >登录</el-button>
        </el-form-item>
      </el-form>

      <div class="auth-footer">
        还没有账号？ <router-link to="/register">立即注册</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
// 1. 从 'element-plus' 分开导入：运行时值 和 TypeScript类型
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useRouter } from 'vue-router';
import { loginApi } from '@/api/modules/auth';
import { useAuthStore } from '@/store/modules/auth';

const router = useRouter();
const authStore = useAuthStore();
const loginFormRef = ref<FormInstance>();
const loading = ref(false);

const loginForm = reactive({
  email: '',
  password: '',
});

const loginRules = reactive<FormRules>({
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
});

const handleLogin = async () => {
  if (!loginFormRef.value) return;
  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true;
      try {
        const res = await loginApi(loginForm);
        authStore.setToken(res.access);
        ElMessage.success('登录成功！');
        // 先跳转到一个临时的dashboard路径
        await router.push('/dashboard');
      } catch (error) {
        console.error("登录失败", error);
      } finally {
        loading.value = false;
      }
    }
  });
};
</script>

