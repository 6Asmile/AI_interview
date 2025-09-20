<template>
  <div class="auth-container">
    <el-card class="auth-card">
      <template #header>
        <div class="card-header">
          <h2>AI 模拟面试平台 - 注册</h2>
        </div>
      </template>

      <el-form
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        label-width="80px"
        @keyup.enter="handleRegister"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="registerForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="registerForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            show-password
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleRegister"
            class="beautiful-button"
            >注册</el-button>
        </el-form-item>
      </el-form>

      <div class="auth-footer">
        已有账号？ <router-link to="/login">立即登录</router-link>
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
import { registerApi } from '@/api/modules/auth';

const router = useRouter();
const registerFormRef = ref<FormInstance>();
const loading = ref(false);

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
});

const registerRules = reactive<FormRules>({
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
});

const handleRegister = async () => {
  if (!registerFormRef.value) return;
  await registerFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true;
      try {
        await registerApi(registerForm);
        ElMessage.success('注册成功！即将跳转到登录页...');
        setTimeout(() => {
          router.push('/login');
        }, 1500);
      } catch (error) {
        console.error("注册失败", error);
      } finally {
        loading.value = false;
      }
    }
  });
};
</script>

