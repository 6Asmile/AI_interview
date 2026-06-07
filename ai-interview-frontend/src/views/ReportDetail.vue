<template>
  <div class="report-page" v-loading="isLoading">
    <div class="report-toolbar">
      <div class="toolbar-copy">
        <p class="report-kicker">Interview Intelligence Report</p>
        <h1>AI 面试评估报告</h1>
        <p>基于 AI 的面试表现分析与改进建议</p>
      </div>
      <el-button 
        type="primary" 
        class="export-button"
        @click="exportToPdf(preExportPdfHook)" 
        :loading="isExporting"
        :icon="Download"
      >
        {{ isExporting ? '导出中...' : '导出为 PDF' }}
      </el-button>
    </div>

    <div ref="reportContentRef">
      <div v-if="reportData && sessionInfo">
        <div class="hero-card page-break-inside-avoid">
          <div class="hero-main">
            <div>
              <p class="hero-kicker">Session Overview</p>
              <h2>面试结果总览</h2>
              <div class="meta-info">
                <span>面试用户: {{ sessionInfo?.user?.username || 'N/A' }}</span>
                <el-divider direction="vertical" />
                <span>面试时间: {{ sessionInfo?.started_at ? new Date(sessionInfo.started_at).toLocaleString() : 'N/A' }}</span>
              </div>
            </div>
            <div class="hero-stats">
              <div class="hero-stat">
                <span>问题数</span>
                <strong>{{ sessionInfo?.question_count || sessionInfo?.questions?.length || 0 }}</strong>
              </div>
              <div class="hero-stat">
                <span>能力项</span>
                <strong>{{ reportData.ability_scores?.length || 0 }}</strong>
              </div>
            </div>
          </div>
        </div>

        <div class="report-card summary-card mb-6 page-break-inside-avoid">
          <div class="report-card__header"><h3>综合评语</h3></div>
          <div class="report-card__body">
            <p class="lead-copy">{{ reportData.overall_comment }}</p>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid">
          <div class="report-card__header"><h3>能力维度分析</h3></div>
          <div class="report-card__body">
            <el-row :gutter="24" align="middle">
              <el-col :xs="24" :sm="12" :md="10">
                <div class="chart-panel">
                  <AbilityRadarChart :ability-scores="reportData.ability_scores || []" />
                </div>
              </el-col>
              <el-col :xs="24" :sm="12" :md="14">
                <div class="ability-table-wrap">
                  <el-table :data="reportData.ability_scores || []" style="width: 100%;">
                    <el-table-column prop="name" label="能力项" />
                    <el-table-column prop="score" label="得分 (0-5)">
                      <template #default="scope">
                        <el-rate v-model="scope.row.score" disabled :max="5" :allow-half="true" />
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-col>
            </el-row>
          </div>
        </div>

        <div class="insight-grid mb-6">
          <div class="report-card accent-card accent-card--success page-break-inside-avoid">
            <div class="report-card__header"><h3>亮点表现</h3></div>
            <div class="report-card__body"><div class="whitespace-pre-wrap formatted-text" v-html="formatText(reportData.strength_analysis)"></div></div>
          </div>

          <div class="report-card accent-card accent-card--warning page-break-inside-avoid">
            <div class="report-card__header"><h3>待改进点</h3></div>
            <div class="report-card__body"><div class="whitespace-pre-wrap formatted-text" v-html="formatText(reportData.weakness_analysis)"></div></div>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid">
          <div class="report-card__header"><h3>改进建议</h3></div>
          <div class="report-card__body">
            <el-timeline class="pl-2">
              <el-timeline-item v-for="(suggestion, index) in (reportData.improvement_suggestions || [])" :key="index" type="primary" hollow>
                <p class="font-medium">建议 {{ index + 1 }}</p>
                <p class="timeline-copy">{{ suggestion }}</p>
              </el-timeline-item>
            </el-timeline>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="reportData.keyword_analysis">
          <div class="report-card__header"><h3>关键词分析</h3></div>
          <div class="report-card__body">
            <div class="keyword-section">
              <p class="keyword-title">匹配的关键词</p>
              <el-tag v-for="kw in (reportData.keyword_analysis.matched_keywords || [])" :key="kw" type="success" class="mr-2 mb-2">{{ kw }}</el-tag>
            </div>
            <el-divider />
            <div class="keyword-section">
              <p class="keyword-title">建议补充的关键词</p>
              <el-tag v-for="kw in (reportData.keyword_analysis.missing_keywords || [])" :key="kw" type="warning" class="mr-2 mb-2">{{ kw }}</el-tag>
            </div>
            <p class="keyword-comment">{{ reportData.keyword_analysis.analysis_comment }}</p>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid">
          <div class="report-card__header"><h3>STAR 法则分析</h3></div>
          <div class="el-card__body">
            <el-table :data="starAnalysisWithQuestionText" style="width: 100%" row-key="question_sequence">
              <el-table-column type="expand">
                <template #default="props">
                  <div class="star-expand-card">
                    <div v-if="props.row.is_behavioral_question">
                      <h4 class="star-title">深度分析</h4>
                      <p class="star-feedback"><strong>总体评价:</strong> {{ props.row.overall_star_feedback }}</p>
                      <div class="space-y-3">
                        <div class="analysis-item"><strong class="text-blue-600">S (Situation):</strong><p class="text-gray-700 pl-2 border-l-2 border-blue-200 ml-1">{{ props.row.situation_analysis }}</p></div>
                        <div class="analysis-item"><strong class="text-green-600">T (Task):</strong><p class="text-gray-700 pl-2 border-l-2 border-green-200 ml-1">{{ props.row.task_analysis }}</p></div>
                        <div class="analysis-item"><strong class="text-purple-600">A (Action):</strong><p class="text-gray-700 pl-2 border-l-2 border-purple-200 ml-1">{{ props.row.action_analysis }}</p></div>
                        <div class="analysis-item"><strong class="text-red-600">R (Result):</strong><p class="text-gray-700 pl-2 border-l-2 border-red-200 ml-1">{{ props.row.result_analysis }}</p></div>
                      </div>
                    </div>
                    <div v-else class="text-gray-500">
                      <p>该问题非典型的行为面试题，不适用 STAR 法则进行深度分析。</p>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="问题" prop="question_text" min-width="300" />
              <el-table-column label="是否行为题" prop="is_behavioral_question" width="120" align="center">
                <template #default="scope"><el-tag :type="scope.row.is_behavioral_question ? 'success' : 'info'" size="small">{{ scope.row.is_behavioral_question ? '是' : '否' }}</el-tag></template>
              </el-table-column>
              <el-table-column label="STAR 法则符合度" prop="conforms_to_star" width="150" align="center">
                <template #default="scope"><el-tag :type="scope.row.conforms_to_star ? 'success' : 'warning'">{{ scope.row.conforms_to_star ? '符合' : '待改进' }}</el-tag></template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        
        <div class="report-card mb-6 page-break-inside-avoid">
          <div class="report-card__header"><h3>面试详情回顾</h3></div>
          <div class="report-card__body">
            <el-collapse v-model="activeCollapse" @change="handleCollapseChange">
              <el-collapse-item v-for="(qa, index) in sessionInfo.questions" :key="qa.id" :name="index">
                <template #title><span class="font-medium">问题 {{ index + 1 }}: {{ qa.question_text }}</span></template>
                <div class="space-y-4 p-2">
                  <div class="detail-bubble detail-bubble--answer">
                    <el-avatar :icon="UserFilled" size="small" class="mt-1 flex-shrink-0"/>
                    <div class="flex-grow">
                      <p class="font-semibold text-sm text-blue-800 mb-1">您的回答</p>
                      <div class="answer-rich-content text-gray-800 text-sm" v-html="formatAnswerHtml(qa.answer_text)"></div>
                    </div>
                  </div>
                  <div class="detail-bubble detail-bubble--feedback"><el-avatar :icon="ChatDotRound" size="small" class="mt-1 flex-shrink-0" /><div class="flex-grow"><p class="font-semibold text-sm text-green-800 mb-1">AI 简评</p><p class="text-gray-800 text-sm">{{ qa.ai_feedback?.feedback || '暂无简评' }}</p></div></div>
                  <div class="ai-reference-answer">
                    <div class="flex justify-between items-center">
                      <h5 class="font-semibold text-yellow-800 text-sm flex items-center gap-2"><el-icon><Opportunity /></el-icon>AI 参考答案</h5>
                      <el-button type="primary" link @click="fetchReferenceAnswer(qa.id)" :loading="referenceAnswerState[qa.id]?.loading">{{ referenceAnswerState[qa.id]?.answer ? '重新获取' : '查看参考答案' }}</el-button>
                    </div>
                    <div v-if="referenceAnswerState[qa.id]?.answer" class="mt-3">
                      <MarkdownRenderer :content="referenceAnswerState[qa.id]?.answer || ''" />
                    </div>
                  </div>
                  <div v-if="qa.analysis_data && qa.analysis_data.length > 0" class="mt-4"><h5 class="font-semibold mb-2 text-gray-600">回答期间情绪波动</h5><EmotionChart :analysis-data="qa.analysis_data" :ref="(el: any) => { if (el) emotionChartRefs[index] = el }" /></div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive, onBeforeUpdate, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { getInterviewReportApi, type InterviewReport } from '@/api/modules/report';
import { getInterviewSessionApi, getAIReferenceAnswerApi, type InterviewSessionItem } from '@/api/modules/interview';
import EmotionChart from '@/components/common/EmotionChart.vue';
import AbilityRadarChart from '@/components/common/AbilityRadarChart.vue';
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue';
import { useExport } from '@/composables/useExport';
import { Download, UserFilled, Opportunity, ChatDotRound } from '@element-plus/icons-vue';
import { ElMessage, ElRow, ElCol, ElDivider, ElTable, ElTableColumn, ElRate, ElTag, ElTimeline, ElTimelineItem, ElCollapse, ElCollapseItem, ElButton, ElAvatar, ElIcon, type CollapseModelValue } from 'element-plus';

const route = useRoute();
const isLoading = ref(true);
const reportData = ref<InterviewReport | null>(null);
const sessionInfo = ref<InterviewSessionItem | null>(null);
const activeCollapse = ref<number[]>([0]);

const reportContentRef = ref<HTMLElement | null>(null);
const { isExporting, exportToPdf } = useExport(reportContentRef, '面试评估报告');

const referenceAnswerState = reactive<Record<number, {loading: boolean, answer: string | null}>>({});

const emotionChartRefs = ref<any[]>([]);
onBeforeUpdate(() => {
  emotionChartRefs.value = [];
});

const handleCollapseChange = (value: CollapseModelValue) => {
  if (!Array.isArray(value)) return;
  setTimeout(() => {
    value.forEach(index => {
      const numericIndex = Number(index);
      if (!isNaN(numericIndex)) {
        const chartRef = emotionChartRefs.value[numericIndex];
        if (chartRef && typeof chartRef.resizeChart === 'function') {
          chartRef.resizeChart();
        }
      }
    });
  }, 300);
};

// [核心修正] 增加健壮性，处理数组和字符串两种情况
const formatText = (text: string | string[] | undefined | null) => {
  if (!text) return '';
  if (Array.isArray(text)) {
    return text.join('<br>');
  }
  return text.replace(/\n/g, '<br>');
};

const formatAnswerHtml = (text: string | undefined | null) => {
  if (!text) return '<p>未作答</p>';

  const trimmed = text.trim();
  if (/<[a-z][\s\S]*>/i.test(trimmed)) {
    return trimmed;
  }

  return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
};

const preExportPdfHook = () => {
  if (sessionInfo.value) {
    activeCollapse.value = Array.from({ length: sessionInfo.value.questions.length }, (_, i) => i);
  }
};

const fetchReferenceAnswer = async (questionId: number) => {
  if (!referenceAnswerState[questionId]) {
    referenceAnswerState[questionId] = { loading: false, answer: null };
  }
  referenceAnswerState[questionId].loading = true;
  try {
    const res = await getAIReferenceAnswerApi(questionId);
    referenceAnswerState[questionId].answer = res.answer;
  } catch (error) {
    ElMessage.error('获取参考答案失败');
  } finally {
    referenceAnswerState[questionId].loading = false;
  }
};

onMounted(async () => {
  const sessionId = route.params.id as string;
  if (!sessionId) {
    ElMessage.error('无效的报告ID');
    isLoading.value = false;
    return;
  }
  try {
    const [reportRes, sessionRes] = await Promise.all([
      getInterviewReportApi(sessionId),
      getInterviewSessionApi(sessionId),
    ]);
    reportData.value = reportRes;
    sessionInfo.value = sessionRes;

    if(activeCollapse.value.includes(0)) {
      await nextTick();
      handleCollapseChange(activeCollapse.value);
    }
  } catch (error) {
    console.error("加载报告数据失败:", error);
    ElMessage.error("加载报告数据失败，请稍后重试。");
  } finally {
    isLoading.value = false;
  }
});

const starAnalysisWithQuestionText = computed(() => {
  if (!reportData.value?.star_analysis || !sessionInfo.value?.questions) {
    return [];
  }
  return reportData.value.star_analysis.map(analysisItem => {
    const question = sessionInfo.value?.questions.find(
      q => q.sequence === analysisItem.question_sequence
    );
    return {
      ...analysisItem,
      question_text: question ? question.question_text : '未知问题'
    };
  });
});
</script>

<style scoped>
.report-page {
  min-height: 100vh;
  padding: 24px 24px 40px;
  background:
    radial-gradient(circle at top left, rgba(76, 146, 255, 0.13), transparent 28%),
    radial-gradient(circle at top right, rgba(33, 185, 146, 0.08), transparent 22%),
    linear-gradient(180deg, #f7faff 0%, #eff4fb 100%);
}

.report-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
  padding: 26px 28px;
  border: 1px solid rgba(201, 214, 236, 0.75);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 20px 44px rgba(47, 74, 119, 0.08);
  backdrop-filter: blur(14px);
}

.report-kicker,
.hero-kicker {
  margin: 0 0 8px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.toolbar-copy h1 {
  margin: 0 0 8px;
  color: #1d2d4d;
  font-size: 30px;
}

.toolbar-copy p:last-child {
  margin: 0;
  color: #6b7a94;
}

.export-button {
  min-height: 48px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 16px 28px rgba(42, 101, 216, 0.18);
}

.hero-card,
.report-card {
  border: 1px solid rgba(207, 219, 238, 0.8);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 22px 50px rgba(43, 67, 108, 0.08);
  overflow: hidden;
}

.hero-card {
  margin-bottom: 24px;
  padding: 30px;
  background: linear-gradient(135deg, rgba(31, 95, 216, 0.95) 0%, rgba(108, 166, 255, 0.92) 100%);
  color: #fff;
}

.hero-main {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.hero-main h2 {
  margin: 0 0 14px;
  font-size: 32px;
}

.meta-info {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: rgba(255, 255, 255, 0.88);
  font-size: 14px;
}

.hero-stats {
  display: flex;
  gap: 12px;
}

.hero-stat {
  min-width: 116px;
  padding: 16px 18px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(10px);
}

.hero-stat span {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.82);
}

.hero-stat strong {
  font-size: 28px;
  line-height: 1;
}

.report-card__header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid #e6edf8;
}

.report-card__header h3 {
  margin: 0;
  color: #1d2e4f;
  font-size: 22px;
}

.report-card__body,
.el-card__body {
  padding: 24px;
}

.summary-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(248, 251, 255, 0.9) 100%);
}

.lead-copy {
  margin: 0;
  color: #30415f;
  font-size: 17px;
  line-height: 1.9;
}

.chart-panel,
.ability-table-wrap {
  padding: 10px;
  border-radius: 22px;
  background: linear-gradient(180deg, #fcfdff 0%, #f5f8fe 100%);
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.accent-card .report-card__body {
  min-height: 180px;
}

.accent-card--success {
  border-color: rgba(163, 222, 185, 0.9);
}

.accent-card--warning {
  border-color: rgba(243, 214, 144, 0.95);
}

.formatted-text {
  line-height: 1.8;
}

.timeline-copy,
.keyword-comment {
  color: #6b7a93;
  line-height: 1.7;
}

.keyword-section + .keyword-section {
  margin-top: 18px;
}

.keyword-title {
  margin: 0 0 12px;
  color: #33435f;
  font-weight: 600;
}

.star-expand-card {
  padding: 16px;
  border: 1px solid #e2eaf7;
  border-radius: 18px;
  background: linear-gradient(180deg, #fafcff 0%, #f3f7fd 100%);
}

.star-title {
  margin: 0 0 12px;
  color: #33435f;
  font-size: 16px;
}

.star-feedback {
  margin-bottom: 16px;
  color: #667792;
}

.detail-bubble {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
}

.detail-bubble--answer {
  background: #edf4ff;
}

.detail-bubble--feedback {
  background: #eefbf4;
}

.answer-rich-content {
  line-height: 1.8;
}

.answer-rich-content :deep(p) {
  margin: 0 0 10px;
}

.answer-rich-content :deep(p:last-child) {
  margin-bottom: 0;
}

.answer-rich-content :deep(ul),
.answer-rich-content :deep(ol) {
  padding-left: 1.4rem;
  margin: 0.5rem 0;
}

.answer-rich-content :deep(li + li) {
  margin-top: 0.35rem;
}

.ai-reference-answer {
  padding: 16px;
  border: 1px dashed #e2b84f;
  border-radius: 18px;
  background: linear-gradient(180deg, #fffaf0 0%, #fff7dd 100%);
}

.ai-reference-answer :deep(.markdown-body) {
  color: #5d4a1f;
  font-size: 14px;
  line-height: 1.85;
}

.ai-reference-answer :deep(.markdown-body h1),
.ai-reference-answer :deep(.markdown-body h2),
.ai-reference-answer :deep(.markdown-body h3) {
  margin-top: 16px;
  color: #6d5416;
  border-bottom-color: rgba(226, 184, 79, 0.35);
}

.ai-reference-answer :deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}

.page-break-inside-avoid {
  break-inside: avoid;
}

.whitespace-pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 900px) {
  .report-page {
    padding: 16px;
  }

  .report-toolbar,
  .hero-main {
    flex-direction: column;
    align-items: flex-start;
  }

  .insight-grid {
    grid-template-columns: 1fr;
  }

  .hero-main h2 {
    font-size: 28px;
  }
}
</style>
