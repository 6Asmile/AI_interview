<template>
  <div class="analysis-report-page" v-loading="isLoading">
    <div class="analysis-toolbar">
      <div class="analysis-toolbar-main">
        <el-page-header @back="goBack" title="返回">
          <template #content><span class="page-title">AI 简历分析报告</span></template>
        </el-page-header>
        <p class="page-copy">基于 AI 的简历分析与优化建议</p>
      </div>
      <el-button class="analysis-export" type="primary" @click="exportToPdf()" :loading="isExporting" :icon="Download">{{ isExporting ? '导出中...' : '导出为 PDF' }}</el-button>
    </div>

    <div ref="reportContentRef">
      <div v-if="reportItem" class="page-break-inside-avoid report-content-wrap">
        <AnalysisReportContent :report="reportItem.report_data" />
      </div>
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
import { ElMessage, ElEmpty, ElPageHeader, ElButton } from 'element-plus';

const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const reportItem = ref<ResumeAnalysisReportItem | null>(null);

const reportContentRef = ref<HTMLElement | null>(null);
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
.analysis-report-page {
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(88, 145, 255, 0.12), transparent 30%),
    linear-gradient(180deg, #f7faff 0%, #eff4fb 100%);
}

.analysis-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
  padding: 24px 28px;
  border: 1px solid rgba(201, 214, 236, 0.75);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 20px 44px rgba(47, 74, 119, 0.08);
  backdrop-filter: blur(14px);
}

.page-title {
  color: #1d2e4f;
  font-size: 24px;
  font-weight: 700;
}

.page-copy {
  margin: 12px 0 0;
  color: #6b7a94;
}

.analysis-export {
  min-height: 48px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 16px 28px rgba(42, 101, 216, 0.18);
}

.report-content-wrap {
  border-radius: 28px;
}

.analysis-report-detail-container :deep(.el-card) {
  break-inside: avoid;
}

:deep(.el-page-header__left) {
  margin-right: 18px;
}

@media (max-width: 900px) {
  .analysis-report-page {
    padding: 16px;
  }

  .analysis-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
