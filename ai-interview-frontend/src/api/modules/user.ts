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