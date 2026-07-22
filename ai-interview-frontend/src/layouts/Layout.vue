<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { RouterView, RouterLink, useRoute } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { useNotificationStore } from '@/store/modules/notification';
import { 
  ElContainer, ElHeader, ElMenu, ElMenuItem, ElSubMenu, 
  ElDropdown, ElDropdownMenu, ElDropdownItem, ElAvatar, 
  ElIcon, ElBadge, ElPopover, ElMain, ElButton, ElDrawer
} from 'element-plus';
import { Bell, Menu as MenuIcon } from '@element-plus/icons-vue';
import NotificationCenter from '@/components/common/NotificationCenter.vue';
import DesktopRequired from '@/components/common/DesktopRequired.vue';
import { ArrowDown, ChatLineRound  } from '@element-plus/icons-vue'; // <-- 【核心修复】导入 ArrowDown

const authStore = useAuthStore();
const notificationStore = useNotificationStore();
const route = useRoute();
const mobileNavOpen = ref(false);

onMounted(() => {
  if (authStore.isAuthenticated) {
    // 首次加载或刷新页面时，获取通知
    notificationStore.fetchNotifications();
  }
});
</script>

<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <el-button class="mobile-menu-button" text circle :icon="MenuIcon" aria-label="打开导航菜单" @click="mobileNavOpen = true" />
      <div class="logo-area">
        <RouterLink to="/dashboard" class="logo-link">IFaceOff</RouterLink>
      </div>

      <nav class="desktop-navigation" aria-label="主导航">
      <el-menu :default-active="route.path" class="main-nav" mode="horizontal" router>
        <el-menu-item index="/dashboard">求职概览</el-menu-item>
        <el-menu-item index="/dashboard/career">求职工作台</el-menu-item>
        <el-menu-item index="/dashboard/community">技术社区</el-menu-item>
        <!-- 【核心新增】聊天/私信入口 -->
        <el-menu-item index="/dashboard/chat">
          <el-icon><ChatLineRound /></el-icon>
          <span>我的私信</span>
        </el-menu-item>
        <el-sub-menu index="/resumes">
          <template #title>简历中心</template>
          <el-menu-item index="/dashboard/resumes">我的简历</el-menu-item>
          <el-menu-item index="/dashboard/generate-resume">AI 简历生成</el-menu-item>
          <el-menu-item index="/dashboard/ai-diagnosis">AI 简历诊断</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="/interviews">
          <template #title>我的面试</template>
          <el-menu-item index="/dashboard/interviews">开始面试</el-menu-item>
          <el-menu-item index="/dashboard/knowledge">知识库</el-menu-item>
          <el-menu-item index="/dashboard/history">面试记录</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/dashboard/tasks">任务中心</el-menu-item>
      </el-menu>
      </nav>

      <div class="right-menu">
        <!-- 通知中心 Popover -->
        <el-popover placement="bottom-end" :width="350" trigger="click">
          <template #reference>
            <el-button text circle aria-label="打开通知中心">
              <el-badge :value="notificationStore.unreadCount" :max="99" :hidden="notificationStore.unreadCount === 0" class="notification-badge">
                <el-icon :size="20" class="bell-icon"><Bell /></el-icon>
              </el-badge>
            </el-button>
          </template>
          <NotificationCenter />
        </el-popover>

        <!-- 用户头像下拉菜单 -->
        <el-dropdown>
          <span class="user-avatar-wrapper">
            <el-avatar :size="32" :src="authStore.avatar || ''" :aria-label="`${authStore.username || '用户'}的头像`">
              {{ authStore.username?.charAt(0).toUpperCase() }}
            </el-avatar>
            <span class="username">{{ authStore.username || '用户' }}</span>
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item>
                <router-link to="/dashboard/profile" class="dropdown-link">个人中心</router-link>
              </el-dropdown-item>
              <el-dropdown-item>
                <router-link to="/dashboard/my-posts" class="dropdown-link">我的文章</router-link>
              </el-dropdown-item>
              <el-dropdown-item>
                <router-link to="/dashboard/settings" class="dropdown-link">AI 设置</router-link>
              </el-dropdown-item>
              <el-dropdown-item>
                <router-link to="/dashboard/tasks" class="dropdown-link">任务中心</router-link>
              </el-dropdown-item>
              <el-dropdown-item divided @click="authStore.logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-drawer v-model="mobileNavOpen" title="导航" direction="ltr" size="280px" append-to-body>
      <nav aria-label="移动端主导航">
        <el-menu :default-active="route.path" router @select="mobileNavOpen = false">
          <el-menu-item index="/dashboard">求职概览</el-menu-item>
          <el-menu-item index="/dashboard/career">求职工作台</el-menu-item>
          <el-menu-item index="/dashboard/community">技术社区</el-menu-item>
          <el-menu-item index="/dashboard/chat">我的私信</el-menu-item>
          <el-menu-item index="/dashboard/resumes">我的简历</el-menu-item>
          <el-menu-item index="/dashboard/interviews">开始面试</el-menu-item>
          <el-menu-item index="/dashboard/knowledge">知识库</el-menu-item>
          <el-menu-item index="/dashboard/history">面试记录</el-menu-item>
          <el-menu-item index="/dashboard/tasks">任务中心</el-menu-item>
          <el-menu-item index="/dashboard/profile">个人中心</el-menu-item>
        </el-menu>
      </nav>
    </el-drawer>

    <el-main class="app-main">
      <RouterView v-slot="{ Component }">
        <DesktopRequired v-if="route.meta.desktopOnly" :feature="String(route.meta.desktopFeature || '')">
          <component :is="Component" />
        </DesktopRequired>
        <component :is="Component" v-else />
      </RouterView>
    </el-main>
  </el-container>
</template>

<style scoped>
.app-layout {
  height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-menu-border-color);
  background-color: #fff;
}

.logo-area {
  display: flex;
  align-items: center;
}

.desktop-navigation { flex: 1; min-width: 0; }

.logo-link {
  font-size: 1.5rem;
  font-weight: bold;
  text-decoration: none;
  color: var(--el-text-color-primary);
}

.main-nav {
  border-bottom: none;
  margin-left: 40px;
}

.mobile-menu-button { display: none; }

.right-menu {
  display: flex;
  align-items: center;
  gap: 24px;
}

.notification-badge {
  cursor: pointer;
  display: flex;
  align-items: center;
}

.bell-icon {
  color: #606266;
  transition: color 0.2s;
}

.bell-icon:hover {
  color: var(--el-color-primary);
}

.user-avatar-wrapper {
  cursor: pointer;
  display: flex;
  align-items: center;
}

.username {
  margin-left: 8px;
  color: var(--el-text-color-regular);
}

.dropdown-link {
  text-decoration: none;
  color: inherit;
  display: block;
  width: 100%;
}

.app-main {
  background-color: #f5f7fa;
  height: calc(100vh - 60px);
  overflow-y: auto;
}

@media (max-width: 1100px) {
  .desktop-navigation { display: none; }
  .mobile-menu-button { display: inline-flex; }
  .app-header { justify-content: flex-start; gap: 10px; padding: 0 14px; }
  .right-menu { margin-left: auto; gap: 8px; }
  .username { display: none; }
}

@media (max-width: 480px) {
  .logo-link { font-size: 1.2rem; }
  .app-main { --el-main-padding: 0; }
}
</style>
