// src/api/modules/auth.ts
import request from '@/api/request';

// 定义请求参数和响应数据的 TypeScript 类型
// 可以在 src/types/api/auth.ts 中定义，这里为方便先写在一起
export interface RegisterData {
  username?: string;
  email?: string;
  password?: string;
}

export interface LoginData {
  email?: string;
  password?: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
}

// 注册API
export const registerApi = (data: RegisterData) => {
  return request({
    url: '/auth/register/',
    method: 'post',
    data,
  });
};

// 登录API
export const loginApi = (data: LoginData): Promise<LoginResponse> => {
  return request({
    url: '/auth/login/',
    method: 'post',
    data,
  });
};