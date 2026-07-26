import { createRouter, createWebHistory } from 'vue-router';
import { staffAuth } from './auth';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'Login', component: () => import('./views/Login.vue') },
    { path: '/security-setup', name: 'SecuritySetup', component: () => import('./views/SecuritySetup.vue') },
    { path: '/register', name: 'StaffRegister', component: () => import('./views/SecuritySetup.vue') },
    { path: '/activate', name: 'Activate', component: () => import('./views/SecuritySetup.vue') },
    {
      path: '/', component: () => import('./views/AdminLayout.vue'), meta: { requiresStaff: true },
      children: [
        { path: '', name: 'Dashboard', component: () => import('./views/Dashboard.vue') },
        { path: 'candidates', name: 'Candidates', component: () => import('./views/Candidates.vue') },
        { path: 'interviews', name: 'Interviews', component: () => import('./views/Interviews.vue') },
        { path: 'interview-config', name: 'InterviewConfig', component: () => import('./views/InterviewConfig.vue') },
        { path: 'agent-config', name: 'AgentConfig', component: () => import('./views/AgentConfig.vue') },
        { path: 'knowledge', name: 'KnowledgeReviews', component: () => import('./views/KnowledgeReviews.vue') },
        { path: 'agent-runs', name: 'AgentRuns', component: () => import('./views/AgentRuns.vue') },
        { path: 'gateway', name: 'Gateway', component: () => import('./views/Gateway.vue') },
        { path: 'operations', name: 'Operations', component: () => import('./views/Operations.vue') },
        { path: 'moderation', name: 'Moderation', component: () => import('./views/Moderation.vue') },
        { path: 'staff', name: 'Staff', component: () => import('./views/Staff.vue') },
        { path: 'audit', name: 'Audit', component: () => import('./views/Audit.vue') },
        { path: 'governance', name: 'Governance', component: () => import('./views/Governance.vue') },
      ],
    },
  ],
});

router.beforeEach(async to => {
  if (!to.meta.requiresStaff) return true;
  await staffAuth.initialize();
  return staffAuth.isAuthenticated.value ? true : { name: 'Login', query: { redirect: to.fullPath } };
});

export default router;
