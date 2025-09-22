<template>
  <div class="callback-container">
    <el-icon class="is-loading" :size="50"><Loading /></el-icon>
    <p>正在通过第三方平台授权，请稍候...</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';
import { connectGitHubApi } from '@/api/modules/user';
import { Loading } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

onMounted(async () => {
  const code = route.query.code as string;
  const flow = localStorage.getItem('oauth_flow'); // 获取流程类型

  if (code) {
    // 清理标记，防止重复执行
    localStorage.removeItem('oauth_flow'); 
    
    if (flow === 'login') {
      // --- 处理登录流程 ---
      try {
        await authStore.loginWithGitHub({ code });
        ElMessage.success('GitHub 授权登录成功！');
        // 跳转已在 action 中处理
      } catch (error) {
        ElMessage.error('GitHub 登录流程失败，请重试。');
        await router.push('/login');
      }
    } else if (flow === 'connect') {
      // --- 处理绑定流程 ---
      try {
        await connectGitHubApi(code);
        ElMessage.success('GitHub 账户绑定成功！');
      } catch (error) {
        ElMessage.error("绑定失败，该 GitHub 账户可能已被其他用户使用。");
      } finally {
        // 无论成功失败，都跳回个人中心
        await router.push('/dashboard/profile');
      }
    } else {
      ElMessage.error('未知的授权流程。');
      await router.push('/login');
    }
  } else {
    const error = route.query.error_description as string;
    ElMessage.warning(error || '您取消了授权。');
    await router.push('/login');
  }
});
</script>

<style scoped>
.callback-container { display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; gap: 20px; color: #606266; }
</style>