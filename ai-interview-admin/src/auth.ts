import { computed, reactive } from 'vue';
import { api, getCsrf } from './api';

export interface StaffAccount {
  id: string;
  email: string;
  display_name: string;
  status: string;
  permissions: string[];
  roles: Array<{ slug: string; name: string }>;
  mfa_enabled: boolean;
  must_change_password: boolean;
}

const state = reactive<{ account: StaffAccount | null; initialized: boolean }>({ account: null, initialized: false });

export const staffAuth = {
  state,
  isAuthenticated: computed(() => Boolean(state.account)),
  has(permission: string) { return Boolean(state.account?.permissions.includes('*') || state.account?.permissions.includes(permission)); },
  async initialize() {
    if (state.initialized) return;
    try { state.account = (await api.get('/auth/session/')).account; } catch { state.account = null; }
    state.initialized = true;
  },
  async login(payload: { email: string; password: string; mfa_code: string }) {
    await getCsrf();
    const result = await api.post('/auth/login/', payload);
    state.account = result.account;
    state.initialized = true;
    return result;
  },
  async logout() {
    try { await api.post('/auth/logout/'); } finally { state.account = null; window.location.href = '/login'; }
  },
};
