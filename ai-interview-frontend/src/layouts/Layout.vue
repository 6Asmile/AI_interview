<!-- src/layouts/Layout.vue -->
<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-content">
        <div class="logo-area" @click="navigateTo('Dashboard')">
          <img alt="logo" src="@/assets/images/logo.png" class="logo-img" />
          <span class="logo-title">IFaceOff</span>
        </div>

        <div class="nav-menu">
          <router-link to="/dashboard" class="nav-item-wrapper">
            <span class="nav-item">仪表盘</span>
          </router-link>
          
          <el-dropdown trigger="hover" class="nav-dropdown">
            <span class="nav-item-wrapper">
              <span class="nav-item">
                简历中心 <el-icon class="icon-down"><arrow-down /></el-icon>
              </span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="navigateTo('ResumeManagement')">我的简历</el-dropdown-item>
                <el-dropdown-item @click="navigateTo('ResumeAIDiagnosis')">AI 简历诊断</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown trigger="hover" class="nav-dropdown">
            <span class="nav-item-wrapper">
              <span class="nav-item">
                我的面试 <el-icon class="icon-down"><arrow-down /></el-icon>
              </span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="navigateTo('History', { tab: 'interviews' })">面试记录</el-dropdown-item>
                <el-dropdown-item @click="navigateTo('History', { tab: 'analysis' })">分析报告</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="user-area">
          <el-dropdown trigger="click">
            <span class="el-dropdown-link">
              <el-avatar :src="authStore.avatar" :size="32">{{ authStore.username?.charAt(0) }}</el-avatar>
              <span class="username">{{ authStore.username || '用户' }}</span>
              <el-icon class="icon-down"><arrow-down /></el-icon>
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
// --- 【核心修复】从 vue-router 导入需要的类型 ---
import type { RouteParamsRaw, LocationQueryRaw } from 'vue-router';
import { ArrowDown } from '@element-plus/icons-vue';

const authStore = useAuthStore();
const router = useRouter();

// --- 【核心修复】使用更精确的类型来定义参数 ---
const navigateTo = (routeName: string, params: RouteParamsRaw | LocationQueryRaw = {}) => {
  // 检查是 query 还是 params
  // 这是一个简单的约定：如果路由是 History，我们就用 query，否则用 params
  if (routeName === 'History') {
      router.push({ name: routeName, query: params as LocationQueryRaw });
  } else {
      router.push({ name: routeName, params: params as RouteParamsRaw });
  }
};
</script>

<style scoped>
/* 样式与之前版本完全相同，无需修改 */
.app-layout { height: 100vh; }
.app-header { background-color: #fff; border-bottom: 1px solid #dcdfe6; padding: 0 24px; }
.header-content { display: flex; align-items: center; height: 100%; }
.logo-area { display: flex; align-items: center; cursor: pointer; }
.logo-img { height: 32px; margin-right: 12px; }
.logo-title { font-size: 20px; font-weight: bold; color: #303133; }
.nav-menu { margin-left: 50px; display: flex; align-items: center; gap: 10px; height: 100%; }
.nav-item-wrapper { padding: 0 20px; height: 100%; display: flex; align-items: center; text-decoration: none; border-bottom: 2px solid transparent; transition: all 0.2s; }
.nav-item-wrapper:hover, .router-link-active { border-bottom-color: var(--el-color-primary); background-color: #f5f7fa; }
.nav-item { color: #303133; font-size: 16px; display: flex; align-items: center; cursor: pointer; }
.router-link-active .nav-item { color: var(--el-color-primary); font-weight: 500; }
.nav-dropdown { height: 100%; }
.nav-dropdown .nav-item-wrapper { outline: none; }
.icon-down { margin-left: 6px; transition: transform 0.2s; }
.nav-item-wrapper:hover .icon-down { transform: rotate(180deg); }
.user-area { margin-left: auto; }
.el-dropdown-link { display: flex; align-items: center; cursor: pointer; }
.username { margin: 0 8px; }
.app-main { background-color: #f7f8fa; padding: 0; }
</style>