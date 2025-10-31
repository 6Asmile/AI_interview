// src/store/modules/system.ts
import { defineStore } from 'pinia';
import { getAISettingsApi } from '@/api/modules/system';
import type { AIModelItem } from '@/api/modules/system';

export const useSystemStore = defineStore('system', {
  state: () => ({
    userDefaultModel: null as AIModelItem | null,
    isLoading: false,
  }),
  getters: {
    activeModelName: (state) => state.userDefaultModel?.name || '系统默认模型',
  },
  actions: {
    async fetchUserSettings() {
      if (this.userDefaultModel) return; // 避免重复获取
      this.isLoading = true;
      try {
        const settings = await getAISettingsApi();
        this.userDefaultModel = settings.ai_model;
      } catch (error) {
        console.error("无法加载用户AI设置", error);
      } finally {
        this.isLoading = false;
      }
    },
  },
});