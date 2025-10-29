import request from '@/api/request';

// ... 类型定义保持不变 ...
export interface Author { id: number; username: string; avatar: string | null; }
export interface Category { id: number; name: string; slug: string; }
export interface Tag { id: number; name: string; slug: string; }
export interface PostListItem { id: number; title: string; author: Author; cover_image: string | null; excerpt: string; category: Category | null; tags: Tag[]; view_count: number; like_count: number; comment_count: number; published_at: string; status: 'draft' | 'published' | 'private'; }
export interface PostDetail extends PostListItem { content: string; word_count: number; read_time: number; }
export type PostFormData = Partial<Omit<PostDetail, 'cover_image'>> & { cover_image_file?: File | null; cover_image?: string | null; };
export interface CommentItem { id: number; author: Author; content: string; created_at: string; parent: number | null; replies: CommentItem[]; }



const createOrUpdatePost = (url: string, method: 'post' | 'patch', data: PostFormData): Promise<PostDetail> => {
  const coverImageFile = data.cover_image_file;

  if (coverImageFile) {
    const formData = new FormData();
    Object.keys(data).forEach(key => {
      const field = key as keyof typeof data;
      // 从 payload 中移除 cover_image 和 cover_image_file，因为一个是 URL，一个是文件对象
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

    return request({
      url,
      method,
      data: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  } else {
    // [核心修正] 如果没有文件，确保不发送任何与文件相关的字段
    const { cover_image_file, ...jsonData } = data;
    return request({ url, method, data: jsonData });
  }
};

export const createPostApi = (data: PostFormData): Promise<PostDetail> => {
  return createOrUpdatePost('/posts/', 'post', data);
};
export const updatePostApi = (id: number, data: PostFormData): Promise<PostDetail> => {
  return createOrUpdatePost(`/posts/${id}/`, 'patch', data);
};

// ... 其他 API 函数保持不变 ...

export const getPostListApi = (params?: any): Promise<PostListItem[]> => { return request({ url: '/posts/', method: 'get', params, }); };
export const getPostDetailApi = (id: number): Promise<PostDetail> => { return request({ url: `/posts/${id}/`, method: 'get', }); };
export const getPostCommentsApi = (postId: number): Promise<CommentItem[]> => { return request({ url: `/posts/${postId}/comments/`, method: 'get', }); };
export const createCommentApi = (postId: number, data: { content: string; parent?: number | null }): Promise<CommentItem> => { return request({ url: `/posts/${postId}/comments/`, method: 'post', data, }); };
export const getCategoryListApi = (): Promise<Category[]> => { return request({ url: '/categories/', method: 'get', }); };
export const getTagListApi = (): Promise<Tag[]> => { return request({ url: '/tags/', method: 'get', }); };