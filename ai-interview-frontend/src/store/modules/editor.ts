// src/store/modules/editor.ts
import { defineStore } from 'pinia';

export const useEditorStore = defineStore('editor', {
  state: () => ({
    isLeftSidebarCollapsed: false,
    isRightSidebarCollapsed: false,
  }),
  actions: {
    toggleLeftSidebar() {
      this.isLeftSidebarCollapsed = !this.isLeftSidebarCollapsed;
    },
    toggleRightSidebar() {
      this.isRightSidebarCollapsed = !this.isRightSidebarCollapsed;
    },
    // 可选：在进入页面时重置状态
    resetState() {
      this.isLeftSidebarCollapsed = false;
      this.isRightSidebarCollapsed = false;
    }
  },
});