import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';

const routes: Array<RouteRecordRaw> = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue') },
  {
    path: '/dashboard',
    component: () => import('@/layouts/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'resumes', name: 'ResumeManagement', component: () => import('@/views/Resume.vue') },
      { path: 'history', name: 'History', component: () => import('@/views/History.vue') },
      { path: 'report/:id', name: 'ReportDetail', component: () => import('@/views/ReportDetail.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue') },
      { path: 'profile', name: 'Profile', component: () => import('@/views/Profile.vue') },
    ],
  },
  // 【最终修正】有且仅有这一个 OAuth 回调路由
  {
    path: '/oauth/callback',
    name: 'OAuthCallback',
    component: () => import('@/views/OAuthCallback.vue'),
  },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore();
  const isAuthenticated = authStore.isAuthenticated;
  const requiresAuth = to.meta.requiresAuth;
  if (requiresAuth && !isAuthenticated) {
    next('/login');
  } else if ((to.name === 'Login' || to.name === 'Register') && isAuthenticated) {
    next('/dashboard');
  } else {
    next();
  }
});

export default router;