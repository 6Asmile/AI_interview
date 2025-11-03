import { defineStore } from 'pinia';
import { getNotificationsApi, markAllNotificationsAsReadApi, markNotificationAsReadApi } from '@/api/modules/notifications';
import type { NotificationItem } from '@/api/modules/notifications';

export const useNotificationStore = defineStore('notification', {
  state: () => ({
    notifications: [] as NotificationItem[],
    unreadCount: 0,
    isLoading: false,
  }),

  actions: {
    // 获取通知列表和未读数量
    async fetchNotifications() {
      this.isLoading = true;
      try {
        const response = await getNotificationsApi({ page_size: 10 }); // 暂不处理分页，先获取最近的
        this.notifications = response.results;
        // 计算未读数量
        this.unreadCount = this.notifications.filter(n => !n.is_read).length;
      } catch (error) {
        console.error("Failed to fetch notifications:", error);
      } finally {
        this.isLoading = false;
      }
    },

    // 标记单条为已读
    async markAsRead(notification: NotificationItem) {
      if (notification.is_read) return; // 如果已读，则不执行任何操作
      
      try {
        await markNotificationAsReadApi(notification.id);
        // 在前端立即更新状态，优化体验
        const target = this.notifications.find(n => n.id === notification.id);
        if (target) {
          target.is_read = true;
          this.unreadCount--;
        }
      } catch (error) {
        console.error("Failed to mark notification as read:", error);
      }
    },

    // 标记全部为已读
    async markAllAsRead() {
      if (this.unreadCount === 0) return;

      try {
        await markAllNotificationsAsReadApi();
        // 在前端立即更新状态
        this.notifications.forEach(n => n.is_read = true);
        this.unreadCount = 0;
      } catch (error) {
        console.error("Failed to mark all notifications as read:", error);
      }
    },
  },
});