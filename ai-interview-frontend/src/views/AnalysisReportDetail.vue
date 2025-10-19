<!-- src/views/AnalysisReportDetail.vue -->
<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
            <span>AI 简历分析报告</span>
            <el-button @click="goBackToEditor">返回编辑器</el-button>
        </div>
      </template>
      <div v-if="isLoading" class="loading-state">
        <el-skeleton :rows="10" animated />
      </div>
      <div v-else-if="reportData">
        <!-- 直接复用抽屉组件的 UI 逻辑 -->
        <AnalysisReportContent :report="reportData.report_data" />
      </div>
      <div v-else class="empty-state">
        <el-empty description="无法加载分析报告" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getAnalysisReportDetailApi, type ResumeAnalysisReportItem } from '@/api/modules/report';
import AnalysisReportContent from '@/components/resume/analysis/AnalysisReportContent.vue';
import { ElMessage, ElSkeleton, ElEmpty } from 'element-plus';

const props = defineProps<{ reportId: string }>();

const router = useRouter();
const reportData = ref<ResumeAnalysisReportItem | null>(null);
const isLoading = ref(true);

onMounted(async () => {
    if (!props.reportId) {
        ElMessage.error('报告ID无效');
        isLoading.value = false;
        return;
    }
    try {
        reportData.value = await getAnalysisReportDetailApi(props.reportId);
    } catch (error) {
        ElMessage.error('加载报告详情失败');
    } finally {
        isLoading.value = false;
    }
});

const goBackToEditor = () => {
    // 假设报告关联的简历ID是 reportData.value.resume
    if(reportData.value) {
        router.push({ name: 'ResumeEditor', params: { id: reportData.value.resume } });
    } else {
        router.back(); // 备用方案
    }
};
</script>

<style scoped>
.page-container { padding: 20px; }
.page-card-header { display: flex; justify-content: space-between; align-items: center; }
</style>