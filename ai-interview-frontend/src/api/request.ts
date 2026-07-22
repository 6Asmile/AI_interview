import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { ElMessage } from 'element-plus';
import { clearAccessToken, getAccessToken, setAccessToken } from '@/auth/token';

export interface ApiErrorEnvelope {
  code: string;
  message: string;
  field_errors: Record<string, unknown>;
  request_id: string;
  retryable: boolean;
}

interface RetryableConfig extends InternalAxiosRequestConfig {
  _authRetry?: boolean;
  suppressErrorToast?: boolean;
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const csrfCookie = () => document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.split('=')[1] || '';

const service = axios.create({
  baseURL,
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: { 'Content-Type': 'application/json;charset=utf-8' },
});

let refreshPromise: Promise<string> | null = null;

export async function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = axios.post(
      `${baseURL}/auth/token/refresh/`,
      {},
      {
        withCredentials: true,
        headers: { 'X-Auth-Mode': 'cookie', 'X-CSRFToken': decodeURIComponent(csrfCookie()) },
        timeout: 15000,
      },
    ).then(({ data }) => {
      if (!data?.access) throw new Error('refresh_missing_access');
      setAccessToken(data.access);
      return data.access as string;
    }).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

service.interceptors.request.use((config: RetryableConfig) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (!config.headers['X-CSRFToken']) {
    const csrf = csrfCookie();
    if (csrf) config.headers['X-CSRFToken'] = decodeURIComponent(csrf);
  }
  return config;
});

service.interceptors.response.use(
  response => response.data,
  async (error: AxiosError<ApiErrorEnvelope | Record<string, any>>) => {
    const config = error.config as RetryableConfig | undefined;
    const status = error.response?.status;
    const url = config?.url || '';
    const authEndpoint = /\/auth\/(login|session|token\/refresh|csrf)\//.test(url);
    if (status === 401 && config && !config._authRetry && !authEndpoint) {
      config._authRetry = true;
      try {
        const access = await refreshAccessToken();
        config.headers.Authorization = `Bearer ${access}`;
        return service(config);
      } catch {
        clearAccessToken();
        window.dispatchEvent(new CustomEvent('ifaceoff:auth-expired'));
      }
    }

    const data = error.response?.data as any;
    const fallback = status === 403 ? '您没有权限执行此操作。'
      : status === 404 ? '请求的资源不存在。'
      : status === 429 ? '操作过于频繁，请稍后再试。'
      : status && status >= 500 ? '服务暂时不可用，请稍后重试。'
      : error.code === 'ECONNABORTED' ? '请求超时，请在任务中心查看后台处理状态。'
      : '网络连接异常。';
    const message = data?.message || data?.detail || data?.error || fallback;
    if (!config?.suppressErrorToast && status !== 401) ElMessage.error(String(message));
    return Promise.reject(error);
  },
);

export default service;
