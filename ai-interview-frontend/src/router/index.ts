import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { checkUnfinishedInterviewApi, abandonUnfinishedInterviewApi } from '@/api/modules/interview';
import { ElMessageBox, ElLoading, ElMessage } from 'element-plus';

const routes: Array<RouteRecordRaw> = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue') },
  { path: '/interview/:id?', name: 'InterviewRoom', component: () => import('@/views/InterviewRoom.vue'), meta: { requiresAuth: true }, props: true },
  { path: '/oauth/callback', name: 'OAuthCallback', component: () => import('@/views/OAuthCallback.vue') },
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
      // 新增：简历编辑器路由
    {
      path: 'resume/edit/:id',
      name: 'ResumeEditor',
      component: () => import('@/views/ResumeEditor.vue'),
    },
    ],
  },
];

const router = createRouter({ history: createWebHistory(), routes });

// 全局标志位，确保“检查中断”在单次应用会话中只执行一次
let hasCheckedForUnfinishedInterview = false;

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore();
  const token = localStorage.getItem('token');

  // 1. 处理需要认证的路由
  if (to.meta.requiresAuth) {
    if (token) {
      // 确保用户信息已加载
      if (!authStore.user) {
        try {
          await authStore.fetchUser();
        } catch (error) {
          authStore.clearAuth();
          return next({ name: 'Login', query: { redirect: to.fullPath } });
        }
      }

      // 【终极核心】检查中断逻辑
      // 只在首次加载并进入需要认证的页面时检查一次
      if (!hasCheckedForUnfinishedInterview) {
        hasCheckedForUnfinishedInterview = true; // 标记为已检查
        try {
          const res = await checkUnfinishedInterviewApi();
          if (res.has_unfinished && res.session_id) {
            // 如果检测到中断，弹窗询问
            await ElMessageBox.confirm(`我们发现您有一个正在进行的 <strong>${res.job_position}</strong> 面试，是否要继续？`, '欢迎回来！', {
              confirmButtonText: '继续面试', cancelButtonText: '放弃', type: 'info', dangerouslyUseHTMLString: true,
            }).then(() => {
              // 用户选择继续，直接导航到面试房间
              return next({ name: 'InterviewRoom', params: { id: res.session_id } });
            }).catch(async () => {
              const loading = ElLoading.service({ text: '正在放弃面试...' });
              try {
                await abandonUnfinishedInterviewApi();
                ElMessage.success('之前的面试已放弃。');
                return next(); // 放弃后，继续前往原定目标 (to)
              } catch (e) {
                ElMessage.error('放弃面试失败');
                return next();
              } finally {
                loading.close();
              }
            });
            return; // 结束守卫，等待用户选择
          }
        } catch (e) { console.error("检查中断面试失败", e); }
      }
      
      // 正常放行
      return next();

    } else {
      // 没有 token，去登录页
      return next({ name: 'Login', query: { redirect: to.fullPath } });
    }
  } 
  // 2. 处理公共路由
  else if (token && (to.name === 'Login' || to.name === 'Register')) {
    return next({ name: 'Dashboard' });
  } 
  // 3. 其他所有情况
  else {
    return next();
  }
});

export default router;