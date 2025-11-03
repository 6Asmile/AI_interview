import request from '@/api/request';
import type { PaginatedResponse } from '@/types/api';

// --- 类型定义 ---
export interface Author { id: number; username: string; avatar: string | null; }
export interface Category { id: number; name: string; slug: string; }
export interface Tag { id: number; name: string; slug: string; }
export interface PostListItem { id: number; title: string; author: Author; cover_image: string | null; excerpt: string; category: Category | null; tags: Tag[]; view_count: number; like_count: number; comment_count: number; published_at: string|null; status: 'draft' | 'published' | 'private';updated_at: string;  }
// 【核心修复】在 PostDetail 接口中添加新的属性
export interface PostDetail extends PostListItem { 
  content: string; 
  word_count: number; 
  read_time: number;
  is_liked: boolean;
  is_bookmarked: boolean;
  is_author_followed: boolean;
}

// PostFormData 用于创建和更新文章时发送给 API 的数据结构
export interface PostFormData {
  title?: string;
  content: string; // 创建时或完整更新时 content 是必需的
  status?: 'draft' | 'published' | 'private';
  excerpt?: string;
  category?: number | null;
  tags?: number[];
  cover_image_file?: File | null;
  cover_image?: string | null;
}
export interface CommentItem { id: number; author: Author; content: string; created_at: string; parent: number | null; replies: CommentItem[]; }
export interface DailyStatsData { labels: string[]; views: number[]; likes: number[]; }


// --- 文章 CRUD API ---
const createOrUpdatePost = (url: string, method: 'post' | 'patch', data: PostFormData | Partial<PostFormData>): Promise<PostDetail> => {
  const coverImageFile = (data as any).cover_image_file;
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
    const { cover_image_file, ...jsonData } = (data as any);
    return request({ url, method, data: jsonData });
  }
};

export const createPostApi = (data: PostFormData): Promise<PostDetail> => createOrUpdatePost('/posts/', 'post', data);

// 【核心修正】允许 updatePostApi 接收一个部分对象 (Partial)
export const updatePostApi = (id: number, data: Partial<PostFormData>): Promise<PostDetail> => createOrUpdatePost(`/posts/${id}/`, 'patch', data);


// --- 列表与详情 API ---
export const getPostListApi = (params?: any): Promise<PaginatedResponse<PostListItem>> => request({ url: '/posts/', method: 'get', params });
export const getPostDetailApi = (id: number): Promise<PostDetail> => request({ url: `/posts/${id}/`, method: 'get' });
export const deletePostApi = (id: number) => request({ url: `/posts/${id}/`, method: 'delete' });

// --- 评论、分类、标签 API ---
export const getPostCommentsApi = (postId: number): Promise<CommentItem[]> => request({ url: `/posts/${postId}/comments/`, method: 'get' });
export const createCommentApi = (postId: number, data: { content: string; parent?: number | null }): Promise<CommentItem> => request({ url: `/posts/${postId}/comments/`, method: 'post', data });
export const getCategoryListApi = (): Promise<PaginatedResponse<Category>> => request({ url: '/categories/', method: 'get' });
export const getTagListApi = (): Promise<PaginatedResponse<Tag>> => request({ url: '/tags/', method: 'get' });

// --- "我的" 相关 API ---
export const getMyPostsApi = (params?: any): Promise<PaginatedResponse<PostListItem>> => request({ url: '/posts/my-posts/', method: 'get', params });
export const getMyPostStatsApi = (): Promise<{ total_views: number; total_likes: number; total_comments: number; total_bookmarks: number; }> => request({ url: '/posts/my-stats/', method: 'get' });
export const getMyDailyStatsApi = (days: number = 7): Promise<DailyStatsData> => request({ url: '/posts/my-daily-stats/', method: 'get', params: { days } });