<template>
  <div class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <div class="logo">AI 模拟面试平台</div>
        <el-menu :default-active="activeIndex" class="app-menu" mode="horizontal" :router="true" background-color="#fff" text-color="#303133" active-text-color="#409EFF">
          <el-menu-item index="/dashboard">仪表盘</el-menu-item>
          <el-menu-item index="/dashboard/resumes">简历中心</el-menu-item>
          <el-menu-item index="/dashboard/history">我的面试</el-menu-item>
        </el-menu>
      </div>
      <div class="user-info">
        <el-avatar :size="32" :src="authStore.avatar || defaultAvatar" />
        <el-dropdown>
          <span class="el-dropdown-link">
            {{ authStore.username || '用户' }}
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
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
import { ref, watch, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
// 【核心修正】从 store 目录导入 useAuthStore
import { useAuthStore } from '@/store/modules/auth';
import { ElMessage, ElMessageBox } from 'element-plus';
import { ArrowDown } from '@element-plus/icons-vue';
import defaultAvatar from '@/assets/images/default_avatar.png';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const activeIndex = ref(route.path);

onMounted(() => {
  if (authStore.isAuthenticated && !authStore.user) {
    authStore.fetchUser();
  }
});

watch(() => route.path, (newPath) => {
  activeIndex.value = newPath;
});

const goToProfile = () => { router.push('/dashboard/profile'); };
const goToSettings = () => { router.push('/dashboard/settings'); };

const handleLogout = () => {
  ElMessageBox.confirm('您确定要退出登录吗？', '提示', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
  }).then(() => {
    authStore.logout();
    ElMessage.success('您已成功退出');
  }).catch(() => {});
};
</script>

<style scoped>
/* 样式保持不变 */
.app-layout { height: 100vh; }
.app-header { display: flex; justify-content: space-between; align-items: center; background-color: #fff; border-bottom: 1px solid #dcdfe6; padding: 0 20px; }
.header-left { display: flex; align-items: center; }
.logo { font-size: 20px; font-weight: bold; margin-right: 40px; }
.app-menu { border-bottom: none; }
.user-info { display: flex; align-items: center; }
.user-info .el-avatar { margin-right: 10px; }
.el-dropdown-link { cursor: pointer; display: flex; align-items: center; }
.app-main { background-color: #fafaf4; }
</style>