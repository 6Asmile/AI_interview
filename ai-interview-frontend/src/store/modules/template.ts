import { defineStore } from 'pinia';
import { getResumeTemplatesApi, type ResumeTemplateItem } from '@/api/modules/template'; // 我们将很快创建这个 API 文件
import { ElMessage } from 'element-plus';

export const useTemplateStore = defineStore('template', {
  state: () => ({
    templates: [] as ResumeTemplateItem[],
    isLoading: false,
  }),
  
  getters: {
    // 根据 slug 查找模板
    getTemplateBySlug: (state) => (slug: string) => {
      return state.templates.find(t => t.slug === slug);
    },
  },

  actions: {
    async fetchTemplates() {
      // 避免重复获取
      if (this.templates.length > 0) return;
      
      this.isLoading = true;
      try {
        this.templates = await getResumeTemplatesApi();
      } catch (error) {
        console.error("获取简历模板失败", error);
        ElMessage.error("无法加载简历模板，请稍后重试。");
      } finally {
        this.isLoading = false;
      }
    },
  },
});