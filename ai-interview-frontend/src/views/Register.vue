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
        
        <!-- 新增：验证码输入框 -->
        <el-form-item label="验证码" prop="code">
          <el-input v-model="registerForm.code" placeholder="请输入6位验证码">
            <template #append>
              <el-button @click="handleSendCode" :disabled="isSendingCode || countdown > 0">
                {{ countdown > 0 ? `${countdown}秒后重发` : '获取验证码' }}
              </el-button>
            </template>
          </el-input>
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
            :loading="loading"
            @click="handleRegister"
            class="beautiful-button"
            >立即注册</el-button
          >
        </el-form-item>
      </el-form>

      <div class="auth-footer">
        已有账号？ <router-link to="/login">立即登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useRouter } from 'vue-router';
import { registerApi, sendCodeApi } from '@/api/modules/auth';

const router = useRouter();
const registerFormRef = ref<FormInstance>();
const loading = ref(false);

// --- 验证码相关状态 ---
const isSendingCode = ref(false);
const countdown = ref(0);
let timer: number | null = null;

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  code: '', // 新增
});

// 自定义邮箱格式校验规则
const validateEmail = (_rule: any, value: any, callback: any) => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!value) {
    return callback(new Error('请输入邮箱'));
  }
  if (!emailRegex.test(value)) {
    return callback(new Error('请输入有效的邮箱地址'));
  }
  callback();
};

const registerRules = reactive<FormRules>({
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [{ validator: validateEmail, trigger: 'blur' }],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 6, message: '验证码必须是6位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
});

// --- 核心逻辑 ---

const handleSendCode = async () => {
  // 先单独校验邮箱字段
  registerFormRef.value?.validateField('email', async (isValid) => {
    if (isValid) {
      isSendingCode.value = true;
      try {
        await sendCodeApi(registerForm.email);
        ElMessage.success('验证码已发送，请注意查收！');
        // 开始倒计时
        countdown.value = 60;
        timer = window.setInterval(() => {
          if (countdown.value > 0) {
            countdown.value--;
          } else if (timer) {
            clearInterval(timer);
            timer = null;
          }
        }, 1000);
      } catch (error) {
        console.error("发送验证码失败", error);
      } finally {
        isSendingCode.value = false;
      }
    } else {
      ElMessage.warning('请先输入正确的邮箱地址');
    }
  });
};

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
        // 错误消息由 axios 拦截器统一处理
      } finally {
        loading.value = false;
      }
    }
  });
};

// 组件卸载时，清除定时器，防止内存泄漏
onUnmounted(() => {
  if (timer) {
    clearInterval(timer);
  }
});
</script>

<style scoped>
/* 样式已全局化，这里可以为空 */
</style>