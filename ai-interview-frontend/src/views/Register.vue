<template>
  <div class="auth-shell">
    <div class="auth-layout">
      <section class="auth-visual">
        <p class="auth-eyebrow">IFaceOff</p>
        <h1>创建账号，开始一套完整的面试训练闭环</h1>
        <p>从简历管理、岗位 JD 分析，到 AI 面试追问、录像复盘和最终报告，集中完成你的面试准备。</p>
        <img src="/hero.webp" alt="AI 模拟面试平台" />
      </section>

      <el-card class="auth-card">
      <div class="card-header">
        <p class="auth-eyebrow">Create Account</p>
        <h2>注册账号</h2>
        <span>填写基础信息后即可进入平台。</span>
      </div>

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
.auth-shell {
  min-height: 100vh;
  padding: 32px;
  background:
    radial-gradient(circle at 12% 10%, rgba(86, 151, 255, 0.18), transparent 30%),
    radial-gradient(circle at 88% 14%, rgba(40, 204, 171, 0.13), transparent 26%),
    linear-gradient(180deg, #f6f9ff 0%, #edf3fb 100%);
}

.auth-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(420px, 0.78fr);
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

.auth-card :deep(.el-card__body) {
  padding: 30px;
}

.card-header {
  margin-bottom: 24px;
}

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
