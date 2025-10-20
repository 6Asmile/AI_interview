<template>
  <div class="analysis-report-detail-container p-4 sm:p-6 lg:p-8" v-loading="isLoading">
    
    <div class="flex justify-between items-center mb-4">
      <el-page-header @back="goBack" title="返回">
        <template #content>
          <span class="text-lg font-medium">AI 简历分析报告</span>
        </template>
      </el-page-header>
      
      <!-- [核心修正] 恢复为简单的导出按钮 -->
      <el-button 
        type="primary" 
        @click="exportToPdf()" 
        :loading="isExporting"
        :icon="Download"
      >
        {{ isExporting ? '导出中...' : '导出为 PDF' }}
      </el-button>
    </div>

    <div ref="reportContentRef">
      <el-card shadow="never" v-if="reportItem">
        <AnalysisReportContent :report="reportItem.report_data" />
      </el-card>
      <el-empty v-else-if="!isLoading" description="报告不存在或加载失败"></el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getAnalysisReportDetailApi, type ResumeAnalysisReportItem } from '@/api/modules/report';
import AnalysisReportContent from '@/components/resume/analysis/AnalysisReportContent.vue';
import { useExport } from '@/composables/useExport';
import { Download } from '@element-plus/icons-vue';
import { ElMessage, ElCard, ElEmpty, ElPageHeader, ElButton } from 'element-plus';

const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const reportItem = ref<ResumeAnalysisReportItem | null>(null);

const reportContentRef = ref<HTMLElement | null>(null);
// [核心修正] 移除 isExportingHtml 和 exportToHtml
const { isExporting, exportToPdf } = useExport(reportContentRef, '简历分析报告');

const goBack = () => {
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
</style>