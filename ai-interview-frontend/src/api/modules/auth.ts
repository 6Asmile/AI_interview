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
}

export interface LoginResponse {
  access: string;
  refresh: string;
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
  });
};

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

// API: 使用从 GitHub 获取的 code，向后端交换我们自己的 JWT Token
// 注意：返回值与我们自己的常规登录 (loginApi) 是一样的
export const githubLoginApi = (data: GitHubLoginData): Promise<LoginResponse> => {
  return request({
    url: '/auth/github/',
    method: 'post',
    data,
  });
};