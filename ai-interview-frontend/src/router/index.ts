// src/router/index.ts
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
// 【修复】移除未使用的 abandonUnfinishedInterviewApi 导入
import { checkUnfinishedInterviewApi } from '@/api/modules/interview';
import { ElMessageBox, ElLoading, ElMessage } from 'element-plus';

const routes: Array<RouteRecordRaw> = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue') },
  // 【注意】顶级面试房间路由已被移除
  // { path: '/interview/:id?', name: 'InterviewRoom', component: () => import('@/views/InterviewRoom.vue'), meta: { requiresAuth: true }, props: true },
  { path: '/oauth/callback', name: 'OAuthCallback', component: () => import('@/views/OAuthCallback.vue') },
  {
    path: '/dashboard',
    component: () => import('@/layouts/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      
      // --- 【核心修改】将面试房间路由移到此处 ---
      { 
        path: 'interview/:id?', 
        name: 'InterviewRoom', 
        component: () => import('@/views/InterviewRoom.vue'), 
        props: true 
      },
      
      { path: 'resumes', name: 'ResumeManagement', component: () => import('@/views/Resume.vue') },
      { path: 'history', name: 'History', component: () => import('@/views/History.vue') },
      { path: 'report/:id', name: 'ReportDetail', component: () => import('@/views/ReportDetail.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue') },
      { path: 'profile', name: 'Profile', component: () => import('@/views/Profile.vue') },
      {
        path: 'resume/edit/:id',
        name: 'ResumeEditor',
        component: () => import('@/views/ResumeEditor.vue'),
        props: true,
      },
      {
        path: 'resume/preview/:id',
        name: 'ResumePreview',
        component: () => import('@/views/ResumePreview.vue'),
        props: true,
        meta: { requiresAuth: true },
      },
      // 【核心新增】分析报告详情页
    { 
        path: 'analysis/:reportId', 
        name: 'AnalysisReportDetail', 
        component: () => import('@/views/AnalysisReportDetail.vue'), 
        props: true 
    },
    { 
      path: 'ai-diagnosis', 
      name: 'ResumeAIDiagnosis',
       component: () => import('@/views/ResumeAIDiagnosis.vue') },
    ],
  },
];

const router = createRouter({ history: createWebHistory(), routes });

// ... (路由守卫 beforeEach 的代码保持不变) ...
let hasCheckedForUnfinishedInterview = false;

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore();
  
  if (!to.meta.requiresAuth) {
    if (authStore.isAuthenticated && (to.name === 'Login' || to.name === 'Register')) {
      return next({ name: 'Dashboard' });
    }
    return next();
  }

  if (!authStore.isAuthenticated) {
    return next({ name: 'Login', query: { redirect: to.fullPath } });
  }

  if (!authStore.user) {
    try {
      await authStore.fetchUser();
    } catch (error) {
      return next({ name: 'Login', query: { redirect: to.fullPath } });
    }
  }

  if (!hasCheckedForUnfinishedInterview) {
    hasCheckedForUnfinishedInterview = true; 
    const loading = ElLoading.service({
      lock: true,
      text: '正在检查您的会话状态...',
      background: 'rgba(0, 0, 0, 0.7)',
    });

    try {
      const res = await checkUnfinishedInterviewApi();
      
      if (res.has_unfinished && res.session_id) {
        loading.setText('发现正在进行的面试...');
        
        try {
          await ElMessageBox.confirm(
            `我们发现您有一个正在进行的 <strong>${res.job_position}</strong> 面试，是否要继续？`,
            '欢迎回来！',
            {
              confirmButtonText: '继续面试',
              cancelButtonText: '稍后处理',
              type: 'info',
              dangerouslyUseHTMLString: true,
            }
          );
          loading.close();
          if (to.name === 'InterviewRoom' && to.params.id === res.session_id) {
            return next();
          } else {
            return next({ name: 'InterviewRoom', params: { id: res.session_id } });
          }
        } catch (action) {
          loading.close();
          ElMessage.info('您可以稍后在“我的面试”中找到并继续这次面试。');
          return next();
        }
      } else {
        loading.close();
        return next();
      }
    } catch (e) {
      console.error("检查中断面试失败", e);
      loading.close();
      return next();
    }
  }

  return next();
});


export default router;