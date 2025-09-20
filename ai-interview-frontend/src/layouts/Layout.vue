<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <div class="logo">AI 模拟面试平台</div>
        <!-- 新增的导航菜单 -->
        <el-menu
          :default-active="activeIndex"
          class="app-menu"
          mode="horizontal"
          :router="true"
          background-color="#fff"
          text-color="#303133"
          active-text-color="#409EFF"
        >
          <el-menu-item index="/dashboard">仪表盘</el-menu-item>
          <el-menu-item index="/dashboard/resumes">简历中心</el-menu-item>
          <el-menu-item index="/dashboard/history">我的面试</el-menu-item>
          
        </el-menu>
      </div>
      <div class="user-info">
        <span>欢迎您！</span>
        <el-dropdown>
          <span class="el-dropdown-link">
            操作<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
               <el-dropdown-item @click="goToSettings">AI 设置</el-dropdown-item>
              <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <el-main class="app-main">
      <!-- 子路由的页面将会在这里显示 -->
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { ElMessage, ElMessageBox } from 'element-plus';
import { ArrowDown } from '@element-plus/icons-vue';

const router = useRouter();
const route = useRoute(); // 获取当前路由信息
const authStore = useAuthStore();

const activeIndex = ref(route.path); // 初始化菜单激活项

// 监听路由变化，更新菜单激活项
watch(() => route.path, (newPath) => {
  activeIndex.value = newPath;
});

const goToSettings = () => {
  router.push('/dashboard/settings');
};

const handleLogout = () => {
  ElMessageBox.confirm('您确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    // 调用 Pinia store 中的 action
    authStore.logout();
    ElMessage.success('您已成功退出');
    // 跳转回登录页
    router.push('/login');
  }).catch(() => {
    // 用户点击了取消
  });
};
</script>

<style scoped>
/* src/layouts/Layout.vue -> <style scoped> */
.app-layout {
  height: 100vh;
  /* 重要：让背景从 #app-container 透过来 */
  background-color: transparent;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 30px;
  /* 毛玻璃效果核心 */
  background-color: rgba(255, 255, 255, 0.6); /* 半透明背景 */
  backdrop-filter: blur(10px); /* 模糊滤镜 */
  border-bottom: 1px solid rgba(255, 255, 255, 0.2); /* 浅色边框 */
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05); /* 轻微阴影 */
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  font-size: 20px;
  font-weight: bold;
  margin-right: 40px;
  color: #303133;
}

.app-menu {
  border-bottom: none;
  /* 菜单也需要透明背景才能融入 */
  background-color: transparent;
}

.user-info {
  display: flex;
  align-items: center;
  color: #303133;
}

.el-dropdown-link {
  cursor: pointer;
  margin-left: 15px;
}

.app-main {
  /* 主内容区域也透明，让背景透出来 */
  background-color: transparent;
}
</style>