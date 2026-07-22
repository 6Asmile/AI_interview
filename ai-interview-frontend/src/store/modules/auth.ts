import { defineStore } from 'pinia';
import router from '@/router';
import { clearAccessToken, getAccessToken, setAccessToken } from '@/auth/token';
import { getUserProfileApi, type UserProfile } from '@/api/modules/user';
import {
  browserSessionApi,
  ensureCsrfApi,
  githubLoginApi,
  loginApi,
  logoutApi,
  type GitHubLoginData,
  type LoginData,
} from '@/api/modules/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getAccessToken() as string | null,
    user: null as UserProfile | null,
    initialized: false,
    initializing: null as Promise<void> | null,
  }),
  getters: {
    isAuthenticated: state => Boolean(state.token && state.user),
    avatar: state => state.user?.avatar || null,
    username: state => state.user?.username,
  },
  actions: {
    setSession(access: string, user?: UserProfile) {
      setAccessToken(access);
      this.token = access;
      if (user) this.user = user;
    },
    async initializeSession() {
      if (this.initialized) return;
      if (this.initializing) return this.initializing;
      this.initializing = (async () => {
        try {
          await ensureCsrfApi();
          const session = await browserSessionApi();
          this.setSession(session.access, session.user);
        } catch {
          this.clearAuth();
        } finally {
          this.initialized = true;
          this.initializing = null;
        }
      })();
      return this.initializing;
    },
    async handleLoginSuccess(access: string) {
      this.setSession(access);
      this.user = await getUserProfileApi();
      this.initialized = true;
      await router.push(this.user.onboarding_completed_at ? '/dashboard' : '/onboarding');
    },
    async loginWithCredentials(data: LoginData) {
      await ensureCsrfApi();
      const response = await loginApi(data);
      await this.handleLoginSuccess(response.access);
    },
    async loginWithGitHub(data: GitHubLoginData) {
      await ensureCsrfApi();
      const response = await githubLoginApi(data);
      await this.handleLoginSuccess(response.access);
    },
    async fetchUser() {
      if (!this.token) return;
      this.user = await getUserProfileApi();
    },
    clearAuth() {
      clearAccessToken();
      this.token = null;
      this.user = null;
    },
    async logout(allSessions = false) {
      try { await logoutApi(allSessions); } catch { /* Local cleanup still applies. */ }
      this.clearAuth();
      await router.push('/login');
    },
  },
});

if (typeof window !== 'undefined') {
  window.addEventListener('ifaceoff:auth-expired', () => {
    const store = useAuthStore();
    store.clearAuth();
    if (router.currentRoute.value.meta.requiresAuth) router.push('/login');
  });
}
