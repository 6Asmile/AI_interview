import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';

// --- 类型定义 ---
export interface Author { id: number; username: string; avatar: string | null; }
export interface Category { id: number; name: string; slug: string; }
export interface Tag { id: number; name: string; slug: string; }
export interface PostListItem { id: number; title: string; author: Author; cover_image: string | null; excerpt: string; category: Category | null; tags: Tag[]; view_count: number; like_count: number; comment_count: number; published_at: string; status: 'draft' | 'published' | 'private'; }
export interface PostDetail extends PostListItem { content: string; word_count: number; read_time: number; }
export interface CommentItem { id: number; author: Author; content: string; created_at: string; parent: number | null; replies: CommentItem[]; }

// 【核心修改】重新定义 PostFormData
export interface PostFormData {
  title?: string;
  content: string; // <-- 将 content 设为必需的 string 类型
  status?: 'draft' | 'published' | 'private';
  excerpt?: string;
  category?: number | null;
  tags?: number[];
  cover_image_file?: File | null;
  cover_image?: string | null;
}

// --- 后续所有函数保持不变 ---
const createOrUpdatePost = (url: string, method: 'post' | 'patch', data: PostFormData): Promise<PostDetail> => {
  const coverImageFile = data.cover_image_file;
  if (coverImageFile) {
    const formData = new FormData();
    Object.keys(data).forEach(key => {
      const field = key as keyof typeof data;
      if (field !== 'cover_image' && field !== 'cover_image_file') {
        const value = data[field];
        if (value !== null && value !== undefined) {
          if (Array.isArray(value)) {
            value.forEach(item => formData.append(field, String(item)));
          } else {
            formData.append(field, String(value));
          }
        }
      }
    });
    formData.append('cover_image', coverImageFile);
    return request({ url, method, data: formData, headers: { 'Content-Type': 'multipart/form-data' } });
  } else {
    const { cover_image_file, ...jsonData } = data;
    return request({ url, method, data: jsonData });
  }
};
export const createPostApi = (data: PostFormData): Promise<PostDetail> => createOrUpdatePost('/posts/', 'post', data);
export const updatePostApi = (id: number, data: PostFormData): Promise<PostDetail> => createOrUpdatePost(`/posts/${id}/`, 'patch', data);
export const getPostListApi = (params?: any): Promise<PaginatedResponse<PostListItem>> => request({ url: '/posts/', method: 'get', params });
export const getPostDetailApi = (id: number): Promise<PostDetail> => request({ url: `/posts/${id}/`, method: 'get' });
export const getPostCommentsApi = (postId: number): Promise<CommentItem[]> => request({ url: `/posts/${postId}/comments/`, method: 'get' });
export const createCommentApi = (postId: number, data: { content: string; parent?: number | null }): Promise<CommentItem> => request({ url: `/posts/${postId}/comments/`, method: 'post', data });
export const getCategoryListApi = (): Promise<PaginatedResponse<Category>> => request({ url: '/categories/', method: 'get' });
export const getTagListApi = (): Promise<PaginatedResponse<Tag>> => request({ url: '/tags/', method: 'get' });