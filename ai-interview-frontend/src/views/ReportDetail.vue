<template>
  <div class="report-detail-container p-4 sm:p-6 lg:p-8" v-loading="isLoading">
    
    <div class="flex justify-end mb-4">
      <el-button 
        type="primary" 
        @click="exportToPdf(preExportPdfHook)" 
        :loading="isExporting"
        :icon="Download"
      >
        {{ isExporting ? '导出中...' : '导出为 PDF' }}
      </el-button>
    </div>

    <div ref="reportContentRef">
      <el-card shadow="never" class="report-card" v-if="reportData && sessionInfo">
         <template #header>
          <div class="card-header flex justify-between items-center"><h1 class="text-2xl font-bold text-gray-800">AI 面试评估报告</h1></div>
          <div class="meta-info text-sm text-gray-500 mt-2"><span>面试用户: {{ sessionInfo?.user?.username || 'N/A' }}</span><el-divider direction="vertical" /><span>面试时间: {{ sessionInfo?.started_at ? new Date(sessionInfo.started_at).toLocaleString() : 'N/A' }}</span></div>
        </template>
        
        <el-card shadow="hover" class="mb-6 page-break-inside-avoid"><template #header><div class="font-semibold text-lg">综合评语</div></template><p class="text-gray-700 leading-relaxed">{{ reportData.overall_comment }}</p></el-card>
        
        <el-card shadow="hover" class="mb-6 page-break-inside-avoid"><template #header><div class="font-semibold text-lg">能力维度分析</div></template><el-row :gutter="20" align="middle"><el-col :xs="24" :sm="12" :md="10"><AbilityRadarChart :ability-scores="reportData.ability_scores" /></el-col><el-col :xs="24" :sm="12" :md="14"><el-table :data="reportData.ability_scores" style="width: 100%;"><el-table-column prop="name" label="能力项" /><el-table-column prop="score" label="得分 (0-5)"><template #default="scope"><el-rate v-model="scope.row.score" disabled :max="5" :allow-half="true" /></template></el-table-column></el-table></el-col></el-row></el-card>

        <el-card shadow="hover" class="mb-6 page-break-inside-avoid"><template #header><div class="font-semibold text-lg">亮点表现</div></template><div class="text-green-700 whitespace-pre-wrap" v-html="formatText(reportData.strength_analysis)"></div></el-card>

        <el-card shadow="hover" class="mb-6 page-break-inside-avoid"><template #header><div class="font-semibold text-lg">待改进点</div></template><div class="text-yellow-700 whitespace-pre-wrap" v-html="formatText(reportData.weakness_analysis)"></div></el-card>

        <el-card shadow="hover" class="mb-6 page-break-inside-avoid"><template #header><div class="font-semibold text-lg">改进建议</div></template><el-timeline class="pl-2"><el-timeline-item v-for="(suggestion, index) in reportData.improvement_suggestions" :key="index" type="primary" hollow><p class="font-medium">建议 {{ index + 1 }}</p><p class="text-gray-600">{{ suggestion }}</p></el-timeline-item></el-timeline></el-card>

        <el-card shadow="hover" class="mb-6 page-break-inside-avoid" v-if="reportData.keyword_analysis"><template #header><div class="font-semibold text-lg">关键词分析</div></template><div><p class="font-medium mb-2">匹配的关键词:</p><el-tag v-for="kw in reportData.keyword_analysis.matched_keywords" :key="kw" type="success" class="mr-2 mb-2">{{ kw }}</el-tag></div><el-divider /><div><p class="font-medium mb-2">建议补充的关键词:</p><el-tag v-for="kw in reportData.keyword_analysis.missing_keywords" :key="kw" type="warning" class="mr-2 mb-2">{{ kw }}</el-tag></div><p class="text-sm text-gray-600 mt-4">{{ reportData.keyword_analysis.analysis_comment }}</p></el-card>

        <el-card shadow="hover" class="mb-6 page-break-inside-avoid">
          <template #header><div class="font-semibold text-lg">STAR 法则分析</div></template>
          <el-table :data="starAnalysisWithQuestionText" style="width: 100%" row-key="question_sequence">
            <el-table-column type="expand">
              <template #default="props">
                <div class="p-4 bg-gray-50 rounded-md">
                  <div v-if="props.row.is_behavioral_question">
                    <h4 class="text-base font-semibold mb-3 text-gray-700">深度分析</h4>
                    <p class="text-sm text-gray-600 mb-4"><strong>总体评价:</strong> {{ props.row.overall_star_feedback }}</p>
                    <div class="space-y-3">
                      <div class="analysis-item"><strong class="text-blue-600">S (Situation):</strong><p class="text-gray-700 pl-2 border-l-2 border-blue-200 ml-1">{{ props.row.situation_analysis }}</p></div>
                      <div class="analysis-item"><strong class="text-green-600">T (Task):</strong><p class="text-gray-700 pl-2 border-l-2 border-green-200 ml-1">{{ props.row.task_analysis }}</p></div>
                      <div class="analysis-item"><strong class="text-purple-600">A (Action):</strong><p class="text-gray-700 pl-2 border-l-2 border-purple-200 ml-1">{{ props.row.action_analysis }}</p></div>
                      <div class="analysis-item"><strong class="text-red-600">R (Result):</strong><p class="text-gray-700 pl-2 border-l-2 border-red-200 ml-1">{{ props.row.result_analysis }}</p></div>
                    </div>
                  </div>
                  <div v-else class="text-gray-500"><p>该问题非典型的行为面试题，不适用 STAR 法则进行深度分析。</p></div>
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
        </el-card>
        
        <el-card shadow="hover" class="mb-6 page-break-inside-avoid">
          <template #header><div class="font-semibold text-lg">面试详情回顾</div></template>
          <el-collapse v-model="activeCollapse" @change="handleCollapseChange">
            <el-collapse-item v-for="(qa, index) in sessionInfo.questions" :key="qa.id" :name="index">
              <template #title><span class="font-medium">问题 {{ index + 1 }}: {{ qa.question_text }}</span></template>
              <div class="space-y-4 p-2">
                <div class="flex items-start gap-3">
                  <el-avatar :icon="UserFilled" size="small" class="mt-1 flex-shrink-0"/>
                  <div class="flex-grow bg-blue-50 p-3 rounded-lg">
                    <p class="font-semibold text-sm text-blue-800 mb-1">您的回答</p>
                    <p class="text-gray-800 text-sm">{{ qa.answer_text || '未作答' }}</p>
                  </div>
                </div>
                <div class="flex items-start gap-3">
                  <el-avatar :icon="ChatDotRound" size="small" class="mt-1 flex-shrink-0" />
                  <div class="flex-grow bg-green-50 p-3 rounded-lg">
                    <p class="font-semibold text-sm text-green-800 mb-1">AI 简评</p>
                    <p class="text-gray-800 text-sm">{{ qa.ai_feedback?.feedback || '暂无简评' }}</p>
                  </div>
                </div>
                <div class="ai-reference-answer p-4 border border-dashed border-yellow-400 bg-yellow-50 rounded-lg">
                  <div class="flex justify-between items-center">
                    <!-- [核心修正] 确保所有标签都正确闭合 -->
                    <h5 class="font-semibold text-yellow-800 text-sm flex items-center gap-2"><el-icon><Opportunity /></el-icon>AI 参考答案</h5>
                    <el-button type="primary" link @click="fetchReferenceAnswer(qa.id)" :loading="referenceAnswerState[qa.id]?.loading">
                      {{ referenceAnswerState[qa.id]?.answer ? '重新获取' : '查看参考答案' }}
                    </el-button>
                  </div>
                  <div v-if="referenceAnswerState[qa.id]?.answer" class="mt-2 text-gray-700 whitespace-pre-wrap text-sm">{{ referenceAnswerState[qa.id]?.answer }}</div>
                </div>
                <div v-if="qa.analysis_data && qa.analysis_data.length > 0" class="mt-4">
                  <h5 class="font-semibold mb-2 text-gray-600">回答期间情绪波动</h5>
                  <EmotionChart :analysis-data="qa.analysis_data" :ref="(el: any) => { if (el) emotionChartRefs[index] = el }" />
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-card>
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
import { useExport } from '@/composables/useExport';
import { Download, UserFilled, Opportunity, ChatDotRound } from '@element-plus/icons-vue';
import { ElMessage, ElCard, ElRow, ElCol, ElDivider, ElTable, ElTableColumn, ElRate, ElTag, ElTimeline, ElTimelineItem, ElCollapse, ElCollapseItem, ElButton, ElAvatar, ElIcon, type CollapseModelValue } from 'element-plus';

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

const formatText = (text: string | undefined | null) => {
  if (!text) return '';
  return text.replace(/\n/g, '<br>');
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
    console.error("加载报告数据失败", error);
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
.report-detail-container {
  max-width: 1200px;
  margin: 0 auto;
}
.whitespace-pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
}
.page-break-inside-avoid {
  page-break-inside: avoid;
}
</style>