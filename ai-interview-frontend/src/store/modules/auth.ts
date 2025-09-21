import { defineStore } from 'pinia';
import router from '@/router';
import { getUserProfileApi, type UserProfile } from '@/api/modules/user';
import { loginApi, githubLoginApi, type LoginData, type GitHubLoginData, type LoginResponse } from '@/api/modules/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null as string | null,
    user: null as UserProfile | null,
  }),
  
  getters: {
    isAuthenticated: (state): boolean => !!state.token,
    avatar: (state): string | null => state.user?.avatar || null,
    username: (state): string | undefined => state.user?.username,
  },
  
  actions: {
    // 【核心修正】将 loginAction 拆分为更小的、职责单一的函数
    
    // 内部函数，只负责设置状态和跳转
    async _handleLoginSuccess(token: string) {
      this.token = token;
      localStorage.setItem('token', token);
      
      try {
        const userProfile = await getUserProfileApi();
        this.user = userProfile;
        await router.push('/dashboard');
      } catch (fetchUserError) {
        console.error("登录成功但获取用户信息失败", fetchUserError);
        this.clearAuth();
        throw fetchUserError; // 将错误继续抛出
      }
    },
    
    // 暴露给常规登录使用
    async loginWithCredentials(data: LoginData) {
        const response = await loginApi(data);
        await this._handleLoginSuccess(response.access);
    },

    // 暴露给 GitHub 登录使用
    async loginWithGitHub(data: GitHubLoginData) {
        const response = await githubLoginApi(data);
        await this._handleLoginSuccess(response.access);
    },
    
    async fetchUser() {
      if (!this.token) return;
      try {
        const userData = await getUserProfileApi();
        this.user = userData;
      } catch (error) {
        console.error("根据 Token 恢复用户信息失败", error);
        this.clearAuth();
        if (router.currentRoute.value.meta.requiresAuth) {
           await router.push('/login');
        }
      }
    },
    
    clearAuth() {
      this.token = null;
      this.user = null;
      localStorage.removeItem('token');
    },

    logout() {
      this.clearAuth();
      router.push('/login');
    },
  },
});