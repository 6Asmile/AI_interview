<template>
  <div class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <!-- 【核心修正】使用图片 Logo -->
        <div class="logo">
          <img src="@/assets/images/logo.png" alt="IFaceOff Logo" class="header-logo" />
          <span>IFaceOff</span>
        </div>
        <el-menu :default-active="activeIndex" class="app-menu" mode="horizontal" :router="true">
          <el-sub-menu index="/dashboard">
            <template #title>仪表盘</template>
            <el-menu-item index="/dashboard" @click="handleIndustrySelect('all')">所有行业</el-menu-item>
            <el-menu-item v-for="industry in jobStore.industriesWithJobs" :key="industry.id" :index="`/dashboard?industry=${industry.id}`" @click="handleIndustrySelect(String(industry.id))">
              {{ industry.name }}
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item index="/dashboard/resumes">简历中心</el-menu-item>
          <el-menu-item index="/dashboard/history">我的面试</el-menu-item>
        </el-menu>
      </div>
      <div class="user-info">
        <el-avatar :size="32" :src="authStore.avatar || defaultAvatar" />
        <el-dropdown>
          <span class="el-dropdown-link">
            {{ authStore.username || '用户' }}<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="goToProfile">个人中心</el-dropdown-item>
              <el-dropdown-item @click="goToSettings">AI 设置</el-dropdown-item>
              <el-dropdown-item @click="handleLogout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </div>
</template>

<script setup lang="ts">
// --- <script> 部分完全不变 ---
import { ref, watch, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { useJobStore } from '@/store/modules/job';
import { ElMessage, ElMessageBox } from 'element-plus';
import { ArrowDown } from '@element-plus/icons-vue';
import defaultAvatar from '@/assets/images/default_avatar.png';
const router = useRouter(); const route = useRoute(); const authStore = useAuthStore(); const jobStore = useJobStore(); const activeIndex = ref(route.path);
onMounted(() => { if (authStore.isAuthenticated && !authStore.user) { authStore.fetchUser(); } jobStore.fetchIndustries(); });
watch(() => route.path, (newPath) => { activeIndex.value = newPath; });
const handleIndustrySelect = (industryId: string) => { jobStore.selectIndustry(industryId); };
const goToProfile = () => { router.push('/dashboard/profile'); };
const goToSettings = () => { router.push('/dashboard/settings'); };
const handleLogout = () => { ElMessageBox.confirm('您确定要退出登录吗？', '提示', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning', }).then(() => { authStore.logout(); ElMessage.success('您已成功退出'); }).catch(() => {}); };
</script>

<style scoped>
/* --- <style> 部分需要为新 Logo 添加样式 --- */
.app-layout { height: 100vh; }
.app-header { display: flex; justify-content: space-between; align-items: center; background-color: #fff; border-bottom: 1px solid #dcdfe6; padding: 0 20px; }
.header-left { display: flex; align-items: center; }
.logo {
  font-size: 20px;
  font-weight: bold;
  margin-right: 40px;
  /* 【新增】让图片和文字在同一行 */
  display: flex;
  align-items: center;
  gap: 10px; /* 图片和文字之间的间距 */
  cursor: pointer;
}
.header-logo {
  height: 40px; /* 控制 logo 图片的高度 */
  width: auto;
}
.app-menu { border-bottom: none; }
.user-info { display: flex; align-items: center; }
.user-info .el-avatar { margin-right: 10px; }
.el-dropdown-link { cursor: pointer; display: flex; align-items: center; }
.app-main { background-color: #f4f7fa; }
</style>