import axios, { AxiosRequestConfig, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  // 【核心修正】将默认超时时间增加到 2 分钟 (120000 毫秒)
  // 这为 AI 生成报告提供了充足的时间。
  timeout: 120000, 
  headers: {
    'Content-Type': 'application/json;charset=utf-8'
  }
});

// 请求拦截器
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore();
    if (authStore.isAuthenticated) {
      config.headers.Authorization = `Bearer ${authStore.token}`;
    }
    return config;
  },
  (error: AxiosError) => {
    ElMessage.error('请求配置错误');
    return Promise.reject(error);
  }
);

// 响应拦截器
service.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error: AxiosError) => {
    let message = '';
    const status = error.response?.status;
    switch (status) {
      case 401:
        message = 'Token 已过期或无效，请重新登录';
        // useAuthStore().logout();
        break;
      case 403:
        message = '您没有权限访问此资源';
        break;
      case 404:
        message = '请求的资源不存在';
        break;
      case 500:
        message = '服务器内部错误';
        break;
      default:
        // 【新增】处理请求超时错误
        if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
          message = '请求超时，AI 可能正在深度思考，请稍后在历史记录中查看报告。';
        } else {
          message = '网络连接异常';
        }
    }
    
    if (error.response?.data) {
      const responseData = error.response.data as any;
      message = responseData.detail || responseData.error || message;
    }
    ElMessage.error(message);
    return Promise.reject(error);
  }
);

export default service;