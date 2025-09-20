// src/store/modules/auth.ts
import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
    state: () => ({
        token: localStorage.getItem('token') || null,
        user: null, // 可以用来存放用户信息
    }),
    getters: {
        isAuthenticated: (state) => !!state.token,
    },
    actions: {
        setToken(token: string) {
            this.token = token;
            localStorage.setItem('token', token);
        },
        logout() {
            this.token = null;
            this.user = null;
            localStorage.removeItem('token');
            // 可以在这里跳转到登录页
            // router.push('/login');
        },
    },
});