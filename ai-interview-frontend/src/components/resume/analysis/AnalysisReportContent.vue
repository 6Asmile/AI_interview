<!-- src/components/resume/analysis/AnalysisReportContent.vue -->
<template>
  <div v-if="report" class="report-container">
    <!-- 1. 总体得分 -->
    <el-card shadow="never" class="report-section">
      <div class="score-section">
        <el-progress type="dashboard" :percentage="report.overall_score" :color="scoreColors" :width="120">
          <template #default="{ percentage }">
            <span class="percentage-value">{{ percentage }}</span>
            <span class="percentage-label">匹配度</span>
          </template>
        </el-progress>
        <div class="score-summary">
          <h3>综合评估</h3>
          <p>这份简历与目标岗位的整体匹配度得分为 {{ report.overall_score }} 分。</p>
        </div>
      </div>
    </el-card>

    <!-- 2. 关键词分析 -->
    <el-card shadow="never" class="report-section">
      <template #header><h3>关键词匹配分析</h3></template>
      <div class="keyword-section">
        <p><strong>岗位核心要求 (JD):</strong></p>
        <div class="tag-group">
          <el-tag v-for="kw in report.keyword_analysis.jd_keywords" :key="kw" type="info" effect="plain">{{ kw }}</el-tag>
        </div>
        <p><strong>简历中匹配的关键词:</strong></p>
        <div class="tag-group">
          <el-tag v-for="kw in report.keyword_analysis.matched_keywords" :key="kw" type="success">{{ kw }}</el-tag>
        </div>
        <p><strong>简历中缺失的关键词:</strong></p>
        <div class="tag-group">
          <el-tag v-for="kw in report.keyword_analysis.missing_keywords" :key="kw" type="warning">{{ kw }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 3. 优势 & 劣势 -->
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never" class="report-section">
          <template #header><h3><el-icon color="#67C23A"><CircleCheckFilled /></el-icon> 亮点分析</h3></template>
          <ul>
            <li v-for="(item, index) in report.strengths_analysis" :key="index">{{ item }}</li>
          </ul>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="report-section">
          <template #header><h3><el-icon color="#F56C6C"><WarningFilled /></el-icon> 待改进点</h3></template>
          <ul>
            <li v-for="(item, index) in report.weaknesses_analysis" :key="index">{{ item }}</li>
          </ul>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 4. 修改建议 -->
    <el-card shadow="never" class="report-section">
      <template #header><h3><el-icon color="#E6A23C"><Opportunity /></el-icon> 具体修改建议</h3></template>
      <!-- 【核心修复】为 v-for 的 div 补全结束标签 -->
      <div v-for="(item, index) in report.suggestions" :key="index" class="suggestion-item">
        <p><strong>针对模块: </strong><el-tag size="small">{{ item.module }}</el-tag></p>
        <p>{{ item.suggestion }}</p>
      </div>
    </el-card>

  </div>
</template>

<script setup lang="ts">
import type { AnalysisReport } from '@/api/modules/resumeEditor';
import { CircleCheckFilled, WarningFilled, Opportunity } from '@element-plus/icons-vue';
import { ElCard, ElProgress, ElTag, ElRow, ElCol, ElIcon } from 'element-plus'; // 确保导入所有使用的组件

defineProps<{
  report: AnalysisReport | null;
}>();

const scoreColors = [
  { color: '#f56c6c', percentage: 50 },
  { color: '#e6a23c', percentage: 80 },
  { color: '#67c23a', percentage: 100 },
];
</script>

<style scoped>
.report-container { display: flex; flex-direction: column; gap: 20px; }
.report-section .el-card__header { padding: 10px 15px; } /* Element Plus 2.x hack */
.report-section :deep(.el-card__header) { padding: 12px 20px; }
.report-section h3 { font-size: 16px; margin: 0; display: flex; align-items: center; gap: 8px; }
.score-section { display: flex; align-items: center; gap: 24px; }
.percentage-value { font-size: 28px; font-weight: bold; }
.percentage-label { font-size: 12px; color: #999; }
.tag-group { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; margin-bottom: 16px; }
ul { padding-left: 20px; margin: 0; }
li { margin-bottom: 8px; }
.suggestion-item { border-bottom: 1px solid #f0f0f0; padding-bottom: 12px; margin-bottom: 12px; }
.suggestion-item:last-child { border-bottom: none; margin-bottom: 0; }
</style>