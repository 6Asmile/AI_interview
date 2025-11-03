import request from '@/api/request';

// 点赞/取消点赞文章
export const toggleLikeApi = (postId: number): Promise<{ status: 'liked' | 'unliked' }> => {
  return request({ url: `/posts/${postId}/like/`, method: 'post' });
};

// 收藏/取消收藏文章
export const toggleBookmarkApi = (postId: number): Promise<{ status: 'bookmarked' | 'unbookmarked' }> => {
  return request({ url: `/posts/${postId}/bookmark/`, method: 'post' });
};

// 关注/取消关注用户
export const toggleFollowApi = (userId: number): Promise<{ status: 'followed' | 'unfollowed' }> => {
  return request({ url: `/users/${userId}/follow/`, method: 'post' });
};