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
    
     async fetchIndustries() {
      if (this.industriesWithJobs.length > 0) return;
      this.isLoading = true;
      try {
        const response = await getJobsByIndustryApi();
        // 【核心修改】从分页响应中提取 results 数组
        // 因为行业列表通常不长，我们在这里暂时不处理分页，直接获取所有数据
        // 如果未来行业非常多，可以考虑在这里实现加载更多的逻辑
        this.industriesWithJobs = response.results; 
      } catch (error) {
        console.error("获取岗位列表失败", error);
        ElMessage.error("无法加载岗位列表，请稍后重试。");
      } finally {
        this.isLoading = false;
      }
    },
  },
});