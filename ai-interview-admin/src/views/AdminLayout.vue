<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { staffAuth } from '@/auth';
import { Bell, Briefcase, Connection, Cpu, DataAnalysis, DocumentChecked, Files, HomeFilled, Lock, Setting, SwitchButton, User, UserFilled } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const allowed = (permission: string | string[]) => (Array.isArray(permission) ? permission : [permission]).some(item => staffAuth.has(item));
const items = computed(() => [
  { path: '/', label: '运行概览', icon: HomeFilled, permission: 'dashboard.view' },
  { path: '/candidates', label: '候选人支持', icon: UserFilled, permission: 'candidate.support' },
  { path: '/interviews', label: '面试会话', icon: Briefcase, permission: 'interview.audit' },
  { path: '/interview-config', label: '模板与评估', icon: Setting, permission: 'template.manage' },
  { path: '/agent-config', label: 'Agent 配置中心', icon: Connection, permission: 'agent_config.view' },
  { path: '/knowledge', label: '知识审批', icon: DocumentChecked, permission: 'knowledge.review' },
  { path: '/agent-runs', label: 'Agent 运行', icon: DataAnalysis, permission: 'interview.audit' },
  { path: '/gateway', label: '模型网关', icon: Cpu, permission: 'gateway.manage' },
  { path: '/operations', label: '任务与健康', icon: Files, permission: 'tasks.manage' },
  { path: '/moderation', label: '社区审核', icon: Bell, permission: 'moderation.manage' },
  { path: '/staff', label: '员工与权限', icon: User, permission: 'staff.manage' },
  { path: '/audit', label: '审计日志', icon: Lock, permission: 'audit.view' },
  { path: '/governance', label: '治理与分析', icon: DataAnalysis, permission: ['analytics.view', 'content.manage', 'notifications.manage', 'feature_flags.manage'] },
].filter(item => allowed(item.permission)));
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="brand"><span class="brand-mark">IF</span><div><strong>iFaceoff</strong><small>员工管理端</small></div></div>
      <nav aria-label="管理端主导航">
        <el-menu :default-active="route.path" router>
          <el-menu-item v-for="item in items" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu>
      </nav>
      <div class="staff-summary">
        <strong>{{ staffAuth.state.account?.display_name }}</strong>
        <small>{{ staffAuth.state.account?.email }}</small>
        <el-button text :icon="SwitchButton" @click="staffAuth.logout">退出员工端</el-button>
      </div>
    </aside>
    <div class="admin-content">
      <header class="admin-topbar"><span>独立员工身份域</span><el-tag type="success" effect="plain">MFA 已验证</el-tag></header>
      <main><router-view /></main>
    </div>
  </div>
</template>

<style scoped>
.admin-shell { min-height: 100vh; display: grid; grid-template-columns: 236px minmax(0, 1fr); background: #f4f6f8; }
.admin-sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; border-right: 1px solid #d9dee5; background: #fff; }
.brand { display: flex; align-items: center; gap: 11px; height: 68px; padding: 0 18px; border-bottom: 1px solid #e5e7eb; }
.brand-mark { display: grid; width: 34px; height: 34px; place-content: center; color: #fff; background: #1d4ed8; font-weight: 800; }
.brand strong, .brand small, .staff-summary strong, .staff-summary small { display: block; }
.brand small, .staff-summary small { color: #667085; font-size: 12px; }
.admin-sidebar nav { flex: 1; padding: 12px 8px; }
.admin-sidebar .el-menu { border-right: 0; }
.staff-summary { padding: 16px 18px; border-top: 1px solid #e5e7eb; overflow-wrap: anywhere; }
.staff-summary .el-button { margin-top: 8px; padding-left: 0; }
.admin-content { min-width: 0; }
.admin-topbar { height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; border-bottom: 1px solid #d9dee5; background: #fff; color: #475467; font-size: 13px; }
</style>
