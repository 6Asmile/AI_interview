<template>
  <div class="analysis-report-content" v-if="report">
    <!-- 综合评估 -->
    <el-card shadow="hover" class="report-block report-block--hero mb-6">
      <div class="hero-layout">
        <el-progress type="dashboard" :percentage="percentage" :color="colors" :width="120">
          <template #default="{ percentage }">
            <span class="text-2xl font-bold">{{ percentage }}</span>
            <span class="text-xs text-gray-500">匹配度</span>
          </template>
        </el-progress>
        <div class="hero-copy">
          <p class="section-kicker">Resume Fit Snapshot</p>
          <h3 class="text-lg font-semibold">综合评估</h3>
          <p class="text-gray-600 mt-2">这份简历与目标岗位的整体匹配度得分为 {{ report.overall_score }} 分。</p>
        </div>
      </div>
    </el-card>

    <!-- [核心修正] 添加能力维度雷达图 -->
    <el-card shadow="hover" class="report-block mb-6">
      <template #header><div class="font-semibold text-lg">能力维度分析</div></template>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
        <div class="subpanel">
          <AbilityRadarChart :ability-scores="report.ability_scores" />
        </div>
        <div class="space-y-4 subpanel">
          <div v-for="ability in report.ability_scores" :key="ability.name" class="flex justify-between items-center">
            <span class="text-sm text-gray-700">{{ ability.name }}</span>
            <div class="flex items-center">
              <el-rate v-model="ability.score" disabled show-score text-color="#ff9900" score-template="{value} 分" :max="5" allow-half />
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 关键词匹配分析 -->
    <el-card shadow="hover" class="report-block mb-6">
       <template #header><div class="font-semibold text-lg">关键词匹配分析</div></template>
       <div class="space-y-4">
        <div class="keyword-panel">
          <p class="font-medium mb-2 text-gray-600">岗位核心要求 (JD):</p>
          <el-tag v-for="kw in report.keyword_analysis.jd_keywords" :key="kw" type="info" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
        <div class="keyword-panel">
          <p class="font-medium mb-2 text-gray-600">简历中匹配的关键词:</p>
          <el-tag v-for="kw in report.keyword_analysis.matched_keywords" :key="kw" type="success" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
        <div class="keyword-panel">
          <p class="font-medium mb-2 text-gray-600">简历中缺失的关键词:</p>
          <el-tag v-for="kw in report.keyword_analysis.missing_keywords" :key="kw" type="warning" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 亮点与改进 -->
     <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
      <el-card shadow="hover" class="report-block report-block--positive">
        <template #header><div class="font-semibold text-lg flex items-center gap-2"><el-icon color="green"><CircleCheckFilled /></el-icon>亮点分析</div></template>
        <ul class="list-disc pl-5 space-y-2 text-gray-700">
          <li v-for="(item, index) in report.strengths_analysis" :key="index">{{ item }}</li>
        </ul>
      </el-card>
      <el-card shadow="hover" class="report-block report-block--warning">
        <template #header><div class="font-semibold text-lg flex items-center gap-2"><el-icon color="orange"><WarningFilled /></el-icon>待改进点</div></template>
        <ul class="list-disc pl-5 space-y-2 text-gray-700">
          <li v-for="(item, index) in report.weaknesses_analysis" :key="index">{{ item }}</li>
        </ul>
      </el-card>
    </div>

    <!-- 具体修改建议 -->
    <el-card shadow="hover" class="report-block">
      <template #header><div class="font-semibold text-lg flex items-center gap-2"><el-icon color="blue"><Edit /></el-icon>具体修改建议</div></template>
      <el-timeline>
        <el-timeline-item
          v-for="(item, index) in report.suggestions"
          :key="index"
          hollow
          type="primary"
        >
          <p class="font-semibold">针对模块: {{ item.module }}</p>
          <p class="text-gray-600 mt-1">{{ item.suggestion }}</p>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AnalysisReport } from '@/api/modules/report';
import { ElCard, ElProgress, ElTag, ElRate, ElTimeline, ElTimelineItem, ElIcon } from 'element-plus';
import { CircleCheckFilled, WarningFilled, Edit } from '@element-plus/icons-vue';
// [核心修正] 导入雷达图组件
import AbilityRadarChart from '@/components/common/AbilityRadarChart.vue';

const props = defineProps<{
  report: AnalysisReport;
}>();

const percentage = computed(() => {
  return props.report?.overall_score || 0;
});

const colors = [
  { color: '#f56c6c', percentage: 60 },
  { color: '#e6a23c', percentage: 80 },
  { color: '#67c23a', percentage: 100 },
];
</script>

<style scoped>
.analysis-report-content {
  display: flex;
  flex-direction: column;
}

.report-block {
  border: 1px solid rgba(207, 219, 238, 0.8);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 22px 50px rgba(43, 67, 108, 0.08);
}

.report-block :deep(.el-card__header) {
  padding: 20px 24px 16px;
  border-bottom: 1px solid #e6edf8;
}

.report-block :deep(.el-card__body) {
  padding: 24px;
}

.report-block--hero {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(247, 250, 255, 0.92) 100%);
}

.hero-layout {
  display: flex;
  align-items: center;
  gap: 28px;
}

.hero-copy {
  flex: 1;
}

.section-kicker {
  margin: 0 0 8px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.subpanel {
  padding: 12px;
  border-radius: 22px;
  background: linear-gradient(180deg, #fcfdff 0%, #f5f8fe 100%);
}

.keyword-panel {
  padding: 16px 18px;
  border: 1px solid #e7edf8;
  border-radius: 18px;
  background: #fbfcff;
}

.report-block--positive {
  border-color: rgba(163, 222, 185, 0.9);
}

.report-block--warning {
  border-color: rgba(243, 214, 144, 0.95);
}

@media (max-width: 768px) {
  .hero-layout {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
