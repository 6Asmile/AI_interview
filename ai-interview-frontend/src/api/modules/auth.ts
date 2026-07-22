// src/api/modules/auth.ts
// 这个文件现在只负责与认证相关的 API 函数。

import request from '@/api/request';

// --- 类型定义 ---
export interface RegisterData {
  username?: string;
  email?: string;
  password?: string;
  code?: string;
}

export interface LoginData {
  email?: string;
  password?: string;
  mfa_code?: string;
}

export interface LoginResponse {
  access: string;
  refresh?: string;
  auth_mode?: 'cookie_refresh' | 'bearer';
}

export interface BrowserSessionResponse {
  access: string;
  user: import('./user').UserProfile;
  auth_mode: 'cookie_refresh';
}

// --- API 函数 ---

export const registerApi = (data: RegisterData) => {
  return request({
    url: '/auth/register/',
    method: 'post',
    data,
  });
};

export const loginApi = (data: LoginData): Promise<LoginResponse> => {
  return request({
    url: '/auth/login/',
    method: 'post',
    data,
    headers: { 'X-Auth-Mode': 'cookie' },
  });
};

export const ensureCsrfApi = (): Promise<{ csrf_token: string }> => request({
  url: '/auth/csrf/', method: 'get', suppressErrorToast: true,
} as any);

export const browserSessionApi = (): Promise<BrowserSessionResponse> => request({
  url: '/auth/session/', method: 'post', headers: { 'X-Auth-Mode': 'cookie' }, suppressErrorToast: true,
} as any);

export const logoutApi = (allSessions = false) => request({
  url: allSessions ? '/auth/logout-all/' : '/auth/logout/',
  method: 'post',
  data: allSessions ? { all_sessions: true } : {},
  suppressErrorToast: true,
} as any);

export const sendCodeApi = (email: string) => {
  return request({
    url: '/auth/send-code/',
    method: 'post',
    data: {
      email,
    },
  });
};

// 定义 GitHub 登录时，需要发送给后端的数据类型
export interface GitHubLoginData {
  code: string;
}

export interface GitHubOAuthStartResponse {
  authorize_url: string;
  expires_in: number;
}

// API: 使用从 GitHub 获取的 code，向后端交换我们自己的 JWT Token
// 注意：返回值与我们自己的常规登录 (loginApi) 是一样的
export const githubLoginApi = (data: GitHubLoginData): Promise<LoginResponse> => {
  return request({
    url: '/auth/github/',
    method: 'post',
    data,
    headers: { 'X-Auth-Mode': 'cookie' },
  });
};

export const startGitHubOAuthApi = (
  flow: 'login' | 'connect' = 'login',
  returnTo = flow === 'connect' ? '/dashboard/profile' : '/dashboard',
): Promise<GitHubOAuthStartResponse> => request({
  url: '/auth/oauth/github/start/',
  method: 'get',
  params: { flow, return_to: returnTo },
});

export const confirmGitHubLinkApi = (linkToken: string, password: string): Promise<LoginResponse> => request({
  url: '/auth/oauth/github/link/confirm/',
  method: 'post',
  data: { link_token: linkToken, password },
  headers: { 'X-Auth-Mode': 'cookie' },
});
