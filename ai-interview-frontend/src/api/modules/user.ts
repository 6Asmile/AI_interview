// src/api/modules/user.ts
import request from '@/api/request';

// 定义用户信息的类型
export interface UserProfile {
  id: number;
  username: string;
  email: string;
  phone: string | null;
  avatar: string | null;
  role: string;
  date_joined: string;
}

// 【新增】定义第三方账户的类型
export interface SocialAccount {
  id: number;
  provider: string; // e.g., 'github'
  uid: string;
  last_login: string;
  date_joined: string;
  extra_data: Record<string, any>;
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  phone: string | null;
  avatar: string | null;
  role: string;
  date_joined: string;
  has_password: boolean;
  socialaccount_set: SocialAccount[]; // 【新增】用户关联的所有第三方账户
}

// API: 获取当前登录用户的个人信息
export const getUserProfileApi = (): Promise<UserProfile> => {
  return request({
    url: '/auth/profile/',
    method: 'get',
  });
};

// API: 更新当前登录用户的个人信息
export const updateUserProfileApi = (data: Partial<UserProfile>): Promise<UserProfile> => {
  return request({
    url: '/auth/profile/',
    method: 'patch', // 使用 PATCH 可以只更新部分字段
    data,
  });
};

// API: 上传头像文件
export const uploadAvatarApi = (formData: FormData): Promise<{ avatar_url: string }> => {
    return request({
        url: '/auth/upload-avatar/',
        method: 'post',
        data: formData,
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
};
// 更新 UserProfile 接口
export interface UserProfile {
    // ...
    has_password: boolean; // 新增
}

// 定义修改密码时需要发送的数据类型
export interface ChangePasswordData {
  old_password?: string;
  new_password1: string;
  new_password2: string;
}

// API: 修改/设置密码
export const changePasswordApi = (data: ChangePasswordData) => {
  return request({
    url: '/auth/password/change/',
    method: 'post',
    data,
  });
};

// 【新增】API: 绑定 GitHub 账户
export const connectGitHubApi = (code: string): Promise<{ message: string }> => {
    return request({
        url: '/auth/github/connect/',
        method: 'post',
        data: { code },
    });
};

// 【核心修正】更新解绑 API 函数
export const disconnectSocialApi = (accountId: number): Promise<{ message: string }> => {
  return request({
    // URL 现在是动态的，并且是 POST 请求
    url: `/auth/social/disconnect/${accountId}/`,
    method: 'post',
    // 不再需要 FormData 或 CSRF Token
  });
};

// 辅助函数，用于从 cookie 中获取 CSRF token
function getCookie(name: string): string | null {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}