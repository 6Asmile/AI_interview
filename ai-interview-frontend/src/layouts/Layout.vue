<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="logo-container" @click="() => router.push('/')">
        <span class="logo-text">IFaceOff</span>
      </div>
      <el-menu mode="horizontal" :router="true" :default-active="activeMenu" class="app-menu" background-color="transparent">
        <el-menu-item index="/dashboard">仪表盘</el-menu-item>
        <el-menu-item index="/dashboard/blog">博客社区</el-menu-item>
        <el-sub-menu index="/resume">
          <template #title>简历中心</template>
          <el-menu-item index="/dashboard/resumes">我的简历</el-menu-item>
          <el-menu-item index="/dashboard/generate-resume">AI 简历生成</el-menu-item>
          <el-menu-item index="/dashboard/ai-diagnosis">AI 简历诊断</el-menu-item>
        </el-sub-menu>
        
        <el-sub-menu index="/interview">
          <template #title>我的面试</template>
          <el-menu-item index="/dashboard/history">面试记录</el-menu-item>
          <el-menu-item index="/dashboard/history">简历评估</el-menu-item>
        </el-sub-menu>
      </el-menu>
      <div class="user-profile">
        <el-dropdown>
           <span class="el-dropdown-link">
            <!-- [核心修正] 恢复 :src 绑定，并正确处理 null 值 -->
            <el-avatar :size="32" class="user-avatar" :src="authStore.avatar ?? undefined">
                {{ authStore.username?.charAt(0).toUpperCase() }}
            </el-avatar>
            <span class="username">{{ authStore.username || '用户' }}</span>
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="() => router.push('/dashboard/profile')">个人中心</el-dropdown-item>
              <el-dropdown-item @click="() => router.push('/dashboard/settings')">AI 设置</el-dropdown-item>
              <el-dropdown-item divided @click="authStore.logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { ElContainer, ElHeader, ElMain, ElMenu, ElMenuItem, ElSubMenu, ElDropdown, ElDropdownMenu, ElDropdownItem, ElAvatar, ElIcon } from 'element-plus';
import { ArrowDown } from '@element-plus/icons-vue';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const activeMenu = computed(() => {
  const { path } = route;
  if (path.startsWith('/dashboard/resumes') || path.startsWith('/dashboard/generate-resume') || path.startsWith('/dashboard/ai-diagnosis')) {
    return '/resume';
  }
  if (path.startsWith('/dashboard/history')) {
    return '/interview';
  }
  return path;
});
</script>

<style scoped>
.app-layout { height: 100vh; }
.app-header { display: flex; align-items: center; justify-content: space-between; background-color: rgba(255, 255, 255, 0.7); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border-bottom: 1px solid #e4e7ed; padding: 0 20px; }
.logo-container { display: flex; align-items: center; cursor: pointer; }
.logo-text { font-size: 20px; font-weight: bold; }
.app-menu { flex-grow: 1; border-bottom: none; margin-left: 50px; }
.user-profile { display: flex; align-items: center; }
.el-dropdown-link { cursor: pointer; display: flex; align-items: center; }
.user-avatar { margin-right: 8px; }
.username { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* [UI/UX 升级] 确保主区域背景透明 */
.app-main { background-color: transparent; padding: 0; }
</style>