<template>
  <div class="analysis-report-content" v-if="report">
    <!-- 综合评估 -->
    <el-card shadow="hover" class="mb-6">
      <div class="flex items-center gap-8">
        <el-progress type="dashboard" :percentage="percentage" :color="colors" :width="120">
          <template #default="{ percentage }">
            <span class="text-2xl font-bold">{{ percentage }}</span>
            <span class="text-xs text-gray-500">匹配度</span>
          </template>
        </el-progress>
        <div>
          <h3 class="text-lg font-semibold">综合评估</h3>
          <p class="text-gray-600 mt-2">这份简历与目标岗位的整体匹配度得分为 {{ report.overall_score }} 分。</p>
        </div>
      </div>
    </el-card>

    <!-- [核心修正] 添加能力维度雷达图 -->
    <el-card shadow="hover" class="mb-6">
      <template #header><div class="font-semibold text-lg">能力维度分析</div></template>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
        <div>
          <AbilityRadarChart :ability-scores="report.ability_scores" />
        </div>
        <div class="space-y-4">
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
    <el-card shadow="hover" class="mb-6">
       <template #header><div class="font-semibold text-lg">关键词匹配分析</div></template>
       <div class="space-y-4">
        <div>
          <p class="font-medium mb-2 text-gray-600">岗位核心要求 (JD):</p>
          <el-tag v-for="kw in report.keyword_analysis.jd_keywords" :key="kw" type="info" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
        <div>
          <p class="font-medium mb-2 text-gray-600">简历中匹配的关键词:</p>
          <el-tag v-for="kw in report.keyword_analysis.matched_keywords" :key="kw" type="success" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
        <div>
          <p class="font-medium mb-2 text-gray-600">简历中缺失的关键词:</p>
          <el-tag v-for="kw in report.keyword_analysis.missing_keywords" :key="kw" type="warning" class="mr-2 mb-2">{{ kw }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 亮点与改进 -->
     <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
      <el-card shadow="hover">
        <template #header><div class="font-semibold text-lg flex items-center gap-2"><el-icon color="green"><CircleCheckFilled /></el-icon>亮点分析</div></template>
        <ul class="list-disc pl-5 space-y-2 text-gray-700">
          <li v-for="(item, index) in report.strengths_analysis" :key="index">{{ item }}</li>
        </ul>
      </el-card>
      <el-card shadow="hover">
        <template #header><div class="font-semibold text-lg flex items-center gap-2"><el-icon color="orange"><WarningFilled /></el-icon>待改进点</div></template>
        <ul class="list-disc pl-5 space-y-2 text-gray-700">
          <li v-for="(item, index) in report.weaknesses_analysis" :key="index">{{ item }}</li>
        </ul>
      </el-card>
    </div>

    <!-- 具体修改建议 -->
    <el-card shadow="hover">
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
import type { AnalysisReport } from '@/api/modules/resumeEditor';
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