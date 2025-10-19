<!-- src/layouts/Layout.vue -->
<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-content">
        <div class="logo-area">
          <img alt="logo" src="@/assets/images/logo.png" class="logo-img" />
          <span class="logo-title">IFaceOff</span>
        </div>
        <div class="nav-menu">
          <router-link to="/dashboard" class="nav-item">仪表盘</router-link>
          
          <!-- 【核心修改】创建下拉菜单 -->
          <el-dropdown trigger="hover" class="nav-dropdown">
            <span class="nav-item">
              简历制作 <el-icon><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="navigateTo('ResumeManagement')">在线制作</el-dropdown-item>
                <el-dropdown-item @click="navigateTo('ResumeAIDiagnosis')">AI简历诊断</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <router-link to="/dashboard/history" class="nav-item">我的面试</router-link>
        </div>
        <div class="user-area">
          <el-dropdown>
            <span class="el-dropdown-link">
              <el-avatar :src="authStore.avatar" :size="32">{{ authStore.username?.charAt(0) }}</el-avatar>
              <span class="username">{{ authStore.username || '用户' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="navigateTo('Profile')">个人中心</el-dropdown-item>
                <el-dropdown-item @click="navigateTo('Settings')">AI 设置</el-dropdown-item>
                <el-dropdown-item divided @click="authStore.logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/store/modules/auth';
import { useRouter } from 'vue-router';
import { ArrowDown } from '@element-plus/icons-vue';

const authStore = useAuthStore();
const router = useRouter();

const navigateTo = (routeName: string) => {
  router.push({ name: routeName });
};
</script>

<style scoped>
.app-layout { height: 100vh; }
.app-header {
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  padding: 0 20px;
}
.header-content {
  display: flex;
  align-items: center;
  height: 100%;
}
.logo-area {
  display: flex;
  align-items: center;
}
.logo-img { height: 32px; margin-right: 12px; }
.logo-title { font-size: 20px; font-weight: 600; }

.nav-menu {
  margin-left: 60px;
  display: flex;
  align-items: center;
  gap: 30px;
}
.nav-item {
  color: #303133;
  text-decoration: none;
  font-size: 15px;
  display: flex;
  align-items: center;
  cursor: pointer;
}
.router-link-active {
  color: var(--el-color-primary);
  font-weight: 500;
}
/* 移除 el-dropdown 的默认 outline */
.nav-dropdown:focus, .nav-dropdown:focus-visible {
    outline: none;
}
.nav-dropdown .nav-item {
    outline: none; /* 确保内部元素也没有 outline */
}


.user-area {
  margin-left: auto;
}
.el-dropdown-link {
  display: flex;
  align-items: center;
  cursor: pointer;
}
.username {
  margin-left: 8px;
}

.app-main {
  background-color: #f0f2f5;
  padding: 0;
}
</style>