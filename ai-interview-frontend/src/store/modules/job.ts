import { defineStore } from 'pinia';
import { getJobsByIndustryApi, type IndustryWithJobsItem } from '@/api/modules/system';
import { ElMessage } from 'element-plus';

export const useJobStore = defineStore('job', {
  state: () => ({
    industriesWithJobs: [] as IndustryWithJobsItem[],
    selectedIndustryId: 'all' as string, // 'all' 代表全部
    isLoading: false,
  }),
  
  getters: {
    // 创建一个计算属性，用于动态筛选
    filteredIndustries: (state) => {
      if (state.selectedIndustryId === 'all') {
        return state.industriesWithJobs;
      }
      return state.industriesWithJobs.filter(
        industry => String(industry.id) === state.selectedIndustryId
      );
    },
  },

  actions: {
    // 设置当前选中的行业
    selectIndustry(industryId: string) {
      this.selectedIndustryId = industryId;
    },
    
    // 从 API 获取所有行业和岗位数据
    async fetchIndustries() {
      if (this.industriesWithJobs.length > 0) return; // 避免重复获取
      this.isLoading = true;
      try {
        this.industriesWithJobs = await getJobsByIndustryApi();
      } catch (error) {
        console.error("获取岗位列表失败", error);
        ElMessage.error("无法加载岗位列表，请稍后重试。");
      } finally {
        this.isLoading = false;
      }
    },
  },
});