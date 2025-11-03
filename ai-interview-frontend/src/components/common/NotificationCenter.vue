<!-- src/components/common/NotificationCenter.vue (新建文件) -->
<template>
  <div class="notification-center">
    <div class="nc-header">
      <h3>通知中心</h3>
      <el-button text type="primary" size="small" @click="handleMarkAllRead">全部已读</el-button>
    </div>
    <div class="nc-list" v-loading="store.isLoading">
      <div v-if="store.notifications.length === 0" class="nc-empty">
        暂无通知
      </div>
      <div 
        v-for="item in store.notifications" 
        :key="item.id" 
        class="nc-item"
        :class="{ unread: !item.is_read }"
        @click="handleItemClick(item)"
      >
        <div class="item-content">
          <p class="item-text" v-html="generateNotificationText(item)"></p>
          <p class="item-time">{{ formatDateTime(item.timestamp, 'YYYY-MM-DD HH:mm') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useNotificationStore } from '@/store/modules/notification';
import type { NotificationItem } from '@/api/modules/notifications';
import { formatDateTime } from '@/utils/format';

const store = useNotificationStore();
const router = useRouter();

const generateNotificationText = (item: NotificationItem): string => {
  const actor = `<strong>${item.actor.username}</strong>`;
  switch (item.verb) {
    case 'liked_post':
      return `${actor} 点赞了你的文章《${item.target?.title || ''}》`;
    case 'commented':
      return `${actor} 评论了你的文章《${item.target?.title || ''}》`;
    case 'replied':
      return `${actor} 回复了你的评论`;
    case 'bookmarked_post':
       return `${actor} 收藏了你的文章《${item.target?.title || ''}》`;
    case 'followed':
      return `${actor} 关注了你`;
    default:
      return '你有一条新通知';
  }
};

const handleItemClick = (item: NotificationItem) => {
  // 1. 标记为已读
  store.markAsRead(item);
  
  // 2. 根据通知类型跳转
  if (item.verb === 'liked_post' || item.verb === 'commented' || item.verb === 'bookmarked_post') {
    if (item.target?.id) {
      router.push({ name: 'PostDetail', params: { id: item.target.id } });
    }
  } else if (item.verb === 'followed') {
    // 可以跳转到关注者的个人主页（如果未来有这个页面）
    // router.push({ name: 'UserProfile', params: { id: item.actor.id } });
  } else if (item.verb === 'replied') {
    // 可以跳转到被回复的评论所在的文章页，并高亮该评论
     if (item.action_object?.post) {
      router.push({ name: 'PostDetail', params: { id: item.action_object.post } });
     }
  }
};

const handleMarkAllRead = () => {
  store.markAllAsRead();
};
</script>

<style scoped>
.notification-center { max-height: 400px; display: flex; flex-direction: column; }
.nc-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; border-bottom: 1px solid #eee; }
.nc-header h3 { margin: 0; font-size: 1rem; }
.nc-list { flex-grow: 1; overflow-y: auto; }
.nc-empty { text-align: center; color: #999; padding: 40px 0; }
.nc-item { padding: 10px 15px; border-bottom: 1px solid #eee; cursor: pointer; transition: background-color 0.2s; }
.nc-item:hover { background-color: #f5f7fa; }
.nc-item.unread { background-color: #ecf5ff; }
.item-text { margin: 0 0 5px; font-size: 0.9rem; color: #333; }
:deep(.item-text strong) { font-weight: 500; color: #000; }
.item-time { margin: 0; font-size: 0.75rem; color: #999; }
</style>