// src/types/api.d.ts

/**
 * 通用的后端分页响应数据结构
 * @template T 列表项的类型
 */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}