// src/router/index.ts
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth'; // 1. 导入 auth store

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/dashboard', // 根路径现在重定向到仪表盘
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
  },
  // 2. 创建一个新的路由，使用 Layout 组件
  {
    path: '/dashboard',
    component: () => import('@/layouts/Layout.vue'),
    meta: { requiresAuth: true }, // 3. 标记这个路由及其所有子路由都需要认证
    children: [
      {
        path: '', // 默认子路由，当访问 /dashboard 时显示
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
      },
        {
        path: 'resumes', // 路径会是 /dashboard/resumes
        name: 'ResumeManagement',
        component: () => import('@/views/Resume.vue'),
      },
       // 新增：面试房间路由
      {
        path: '/interview/:id', // 使用动态路由参数 :id
        name: 'InterviewRoom',
        component: () => import('@/views/InterviewRoom.vue'),
        meta: { requiresAuth: true }, // 这个页面也需要登录才能访问
      },
       {
      path: 'settings', // 路径为 /dashboard/settings
      name: 'Settings',
      component: () => import('@/views/Settings.vue'),
       },
        {
      path: 'history',
      name: 'History',
      component: () => import('@/views/History.vue'),
      },
       {
      path: 'report/:id', // 报告详情页
      name: 'ReportDetail',
      component: () => import('@/views/ReportDetail.vue'),
       },
      // 以后可以在这里添加更多需要布局的页面
      // {
      //   path: 'profile',
      //   name: 'Profile',
      //   component: () => import('@/views/Profile.vue'),
      // },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 4. 创建全局前置路由守卫
router.beforeEach((to, _from, next) => {
  // 在守卫函数内部获取 store 实例
  const authStore = useAuthStore();

  const isAuthenticated = authStore.isAuthenticated;
  const requiresAuth = to.meta.requiresAuth;

  // 逻辑判断
  if (requiresAuth && !isAuthenticated) {
    // 如果目标路由需要认证，但用户未登录
    next('/login'); // 重定向到登录页
  } else if ((to.name === 'Login' || to.name === 'Register') && isAuthenticated) {
    // 如果用户已登录，但试图访问登录或注册页
    next('/dashboard'); // 重定向到仪表盘
  } else {
    // 其他所有情况，正常放行
    next();
  }
});

export default router;