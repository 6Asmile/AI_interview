// src/api/modules/common.ts
import request from '@/api/request';

// 移除: import { useAuthStore } from '@/store/modules/auth';

/**
 * 通用的文件上传 API
 * ...
 */
export const uploadFileApi = (file: File, dir: string = 'uploads'): Promise<{ file_url: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('dir', dir);

  return request({
    url: '/upload/',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};