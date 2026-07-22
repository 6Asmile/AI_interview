import axios, { type AxiosRequestConfig } from 'axios';

const baseURL = import.meta.env.VITE_ADMIN_API_BASE_URL || '/api/admin/v1';
const csrf = () => decodeURIComponent(document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.split('=')[1] || '');

const client = axios.create({ baseURL, withCredentials: true, timeout: 30000 });
client.interceptors.request.use(config => {
  if (!['get', 'head', 'options'].includes(String(config.method).toLowerCase())) {
    config.headers['X-CSRFToken'] = csrf();
    if (!config.headers['Idempotency-Key']) config.headers['Idempotency-Key'] = crypto.randomUUID();
  }
  return config;
});
export const api = {
  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return (await client.get<T>(url, config)).data;
  },
  async post<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return (await client.post<T>(url, data, config)).data;
  },
  async patch<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return (await client.patch<T>(url, data, config)).data;
  },
};

export const getCsrf = () => api.get('/auth/csrf/');
export const writeConfig = (reason: string): AxiosRequestConfig => ({
  headers: { 'Idempotency-Key': crypto.randomUUID() },
  data: { operation_reason: reason },
});
