<template>
  <div class="analysis-report-detail-container p-4 sm:p-6 lg:p-8" v-loading="isLoading">
    
    <!-- [核心修改] 增加顶部操作栏，包含返回和导出按钮 -->
    <div class="flex justify-between items-center mb-4">
      <el-page-header @back="goBack" title="返回列表">
        <template #content>
          <span class="text-lg font-medium">AI 简历分析报告</span>
        </template>
      </el-page-header>
      <el-button 
        type="primary" 
        @click="exportToPdf" 
        :loading="isExporting"
        :icon="Download"
      >
        {{ isExporting ? '导出中...' : '导出为 PDF' }}
      </el-button>
    </div>

    <!-- [核心修改] 将 ref 绑定到需要导出的 el-card -->
    <el-card shadow="never" v-if="reportItem" ref="reportContentRef">
      <AnalysisReportContent :report="reportItem.report_data" />
    </el-card>

    <el-empty v-else-if="!isLoading" description="报告不存在或加载失败"></el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getAnalysisReportDetailApi, type ResumeAnalysisReportItem } from '@/api/modules/report';
import AnalysisReportContent from '@/components/resume/analysis/AnalysisReportContent.vue';
import { ElMessage, ElCard, ElEmpty, ElPageHeader, ElButton } from 'element-plus';
// [核心修改] 导入 composable 和图标
import { usePdfExport } from '@/composables/usePdfExport';
import { Download } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const reportItem = ref<ResumeAnalysisReportItem | null>(null);

// [核心修改] 设置 PDF 导出
const reportContentRef = ref<HTMLElement | null>(null);
const { isExporting, exportToPdf } = usePdfExport(reportContentRef, '简历分析报告');


const goBack = () => {
  // 假设历史记录页的 name 是 'History'
  router.push({ name: 'History' });
};

onMounted(async () => {
  const reportId = route.params.reportId as string;
  if (!reportId) {
    ElMessage.error("无效的报告ID");
    isLoading.value = false;
    return;
  }

  try {
    reportItem.value = await getAnalysisReportDetailApi(reportId);
  } catch (error) {
    console.error("加载简历分析报告详情失败", error);
    ElMessage.error("加载报告失败");
  } finally {
    isLoading.value = false;
  }
});
</script>

<style scoped>
.analysis-report-detail-container {
  max-width: 1000px;
  margin: 0 auto;
}
.page-container { padding: 20px; }
.page-card-header { display: flex; justify-content: space-between; align-items: center; }
</style>