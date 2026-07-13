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

        <div class="verification-grid mb-6" v-if="hasVerificationChain">
          <div class="report-card verification-card page-break-inside-avoid">
            <div class="report-card__header"><h3>已验证能力</h3></div>
            <div class="report-card__body">
              <el-tag v-for="item in (reportData.verified_abilities || [])" :key="item" type="success" class="mr-2 mb-2">{{ item }}</el-tag>
              <p v-if="!reportData.verified_abilities?.length" class="muted-copy">暂无明确验证能力。</p>
            </div>
          </div>
          <div class="report-card verification-card page-break-inside-avoid">
            <div class="report-card__header"><h3>未验证风险</h3></div>
            <div class="report-card__body">
              <el-tag v-for="item in (reportData.unverified_risks || [])" :key="item" type="warning" class="mr-2 mb-2">{{ item }}</el-tag>
              <p v-if="!reportData.unverified_risks?.length" class="muted-copy">暂无明显未验证风险。</p>
            </div>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="reportData.template_snapshot || reportData.coverage_summary">
          <div class="report-card__header"><h3>评估体系快照</h3></div>
          <div class="report-card__body">
            <div class="evaluation-snapshot">
              <div>
                <span>面试模板</span>
                <strong>{{ reportData.template_snapshot?.template_name || '未记录' }}</strong>
              </div>
              <div>
                <span>评分模式</span>
                <strong>{{ reportData.evaluation_version?.mode || 'rule_ai_dual' }}</strong>
              </div>
              <div>
                <span>覆盖缺口</span>
                <strong>{{ reportData.coverage_summary?.coverage_gaps?.length || 0 }}</strong>
              </div>
            </div>
            <div v-if="reportData.coverage_summary?.coverage_gaps?.length" class="snapshot-tags">
              <el-tag v-for="item in reportData.coverage_summary.coverage_gaps" :key="item" type="warning">{{ item }}</el-tag>
            </div>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="qualityBreakdownWithQuestion.length">
          <div class="report-card__header"><h3>问题质量验证链路</h3></div>
          <div class="report-card__body">
            <el-table :data="qualityBreakdownWithQuestion" style="width: 100%;">
              <el-table-column label="问题" prop="question_text" min-width="260" />
              <el-table-column label="质量分" width="110">
                <template #default="scope">
                  <span class="score-badge">{{ scope.row.quality_score ?? '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="追问方向" prop="follow_up_target" min-width="220" />
              <el-table-column label="追问依据" prop="follow_up_reason" min-width="220" />
            </el-table>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="agentTraceRows.length">
          <div class="report-card__header"><h3>Agent 决策审计</h3></div>
          <div class="report-card__body">
            <el-table :data="agentTraceRows" style="width: 100%;" class="agent-trace-table">
              <el-table-column label="轮次" width="90">
                <template #default="scope">
                  <span>{{ scope.row.sequenceLabel }}</span>
                </template>
              </el-table-column>
              <el-table-column label="事件/阶段" width="160">
                <template #default="scope">
                  <div class="trace-stack">
                    <strong>{{ scope.row.event }}</strong>
                    <span>{{ stageLabel(scope.row.stage) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="节点链路" min-width="220">
                <template #default="scope">
                  <div class="trace-node-list">
                    <el-tag v-for="node in scope.row.nodeOrder" :key="node" size="small" effect="plain">{{ node }}</el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="工具/RAG" min-width="230">
                <template #default="scope">
                  <div class="trace-stack">
                    <span>{{ scope.row.toolSummary }}</span>
                    <small>{{ scope.row.retrievalSummary }}</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="计划与校验" min-width="260">
                <template #default="scope">
                  <div class="trace-stack">
                    <span>{{ scope.row.planTarget || '未记录计划目标' }}</span>
                    <small v-if="scope.row.validationText">校验：{{ scope.row.validationText }}</small>
                    <small v-if="scope.row.fallback_reason">降级：{{ scope.row.fallback_reason }}</small>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="environmentAuditRows.length">
          <div class="report-card__header"><h3>环境感知与评分隔离</h3></div>
          <div class="report-card__body">
            <p class="audit-note">多模态环境信号只用于转写确认、恢复和追问策略，不直接进入候选人能力评分。</p>
            <el-table :data="environmentAuditRows" style="width: 100%;" class="agent-trace-table">
              <el-table-column label="轮次" prop="sequenceLabel" width="90" />
              <el-table-column label="信号质量" width="180">
                <template #default="scope">
                  <div class="trace-stack">
                    <strong>{{ scope.row.signalQualityLabel }}</strong>
                    <small>视觉：{{ scope.row.visualSignalLabel }}</small>
                    <small>帧数：{{ scope.row.frame_count }}</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="ASR/音频" width="180">
                <template #default="scope">
                  <div class="trace-stack">
                    <span>{{ scope.row.has_audio ? '有语音记录' : '无语音记录' }}</span>
                    <small>置信度：{{ scope.row.asrConfidenceText }}</small>
                    <small>{{ scope.row.suggestedActionLabel }}</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="环境风险" min-width="220">
                <template #default="scope">
                  <div class="trace-node-list" v-if="scope.row.risk_flags.length">
                    <el-tag v-for="flag in scope.row.risk_flags" :key="flag" type="warning" size="small" effect="plain">
                      {{ environmentRiskLabel(flag) }}
                    </el-tag>
                  </div>
                  <span v-else class="muted-copy">无明显环境风险</span>
                </template>
              </el-table-column>
              <el-table-column label="评分策略" min-width="260">
                <template #default="scope">
                  <div class="trace-stack">
                    <el-tag :type="scope.row.use_for_scoring ? 'danger' : 'success'" size="small">
                      {{ scope.row.use_for_scoring ? '进入评分' : '不进入评分' }}
                    </el-tag>
                    <small>{{ scope.row.scoringPolicyText }}</small>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="report-card mb-6 page-break-inside-avoid" v-if="agentToolCallRows.length || agentMemoryEventRows.length">
          <div class="report-card__header"><h3>Agent 工具与记忆链路</h3></div>
          <div class="report-card__body">
            <div v-if="agentToolCallRows.length" class="audit-section">
              <p class="keyword-title">工具调用</p>
              <el-table :data="agentToolCallRows" style="width: 100%;" class="agent-trace-table">
                <el-table-column label="轮次" prop="sequenceLabel" width="80" />
                <el-table-column label="节点/工具" width="220">
                  <template #default="scope">
                    <div class="trace-stack">
                      <strong>{{ scope.row.tool_name }}</strong>
                      <small>{{ scope.row.node_name || '未记录节点' }}</small>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template #default="scope">
                    <el-tag :type="scope.row.status === 'success' ? 'success' : scope.row.status === 'degraded' ? 'warning' : 'danger'" size="small">
                      {{ scope.row.statusLabel }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="检索摘要" min-width="260">
                  <template #default="scope">
                    <div class="trace-stack">
                      <span>{{ scope.row.outputText }}</span>
                      <small>{{ scope.row.retrievalSummary }}</small>
                      <small v-if="scope.row.error_message">原因：{{ scope.row.error_message }}</small>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div v-if="agentMemoryEventRows.length" class="audit-section">
              <p class="keyword-title">记忆事件</p>
              <el-table :data="agentMemoryEventRows" style="width: 100%;" class="agent-trace-table">
                <el-table-column label="轮次" prop="sequenceLabel" width="80" />
                <el-table-column label="类型/来源" width="180">
                  <template #default="scope">
                    <div class="trace-stack">
                      <strong>{{ scope.row.event_type }}</strong>
                      <small>{{ scope.row.source_node || '未记录来源' }}</small>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="记忆键" prop="memory_key" width="180" />
                <el-table-column label="重要性" width="100">
                  <template #default="scope">
                    <el-tag size="small" effect="plain">{{ scope.row.importance }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="摘要" prop="valueText" min-width="300" />
              </el-table>
            </div>
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
                  <div class="detail-bubble detail-bubble--feedback">
                    <el-avatar :icon="ChatDotRound" size="small" class="mt-1 flex-shrink-0" />
                    <div class="flex-grow">
                      <div class="feedback-title-row">
                        <p class="font-semibold text-sm text-green-800 mb-1">AI 简评</p>
                        <span v-if="qa.ai_feedback?.quality_score !== undefined" class="mini-score">{{ qa.ai_feedback.quality_score }} 分</span>
                      </div>
                      <p class="text-gray-800 text-sm">{{ qa.ai_feedback?.feedback || '暂无简评' }}</p>
                      <p v-if="qa.ai_feedback?.follow_up_target" class="feedback-extra">追问方向：{{ qa.ai_feedback.follow_up_target }}</p>
                      <p v-if="qa.ai_feedback?.follow_up_reason" class="feedback-extra">追问依据：{{ qa.ai_feedback.follow_up_reason }}</p>
                    </div>
                  </div>
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
import { ref, onMounted, computed, reactive, onBeforeUpdate, nextTick, defineAsyncComponent } from 'vue';
import { useRoute } from 'vue-router';
import { getInterviewReportApi, type InterviewReport } from '@/api/modules/report';
import {
  getInterviewSessionApi,
  getAIReferenceAnswerApi,
  getInterviewAgentTracesApi,
  getInterviewAgentToolCallsApi,
  getInterviewAgentMemoryEventsApi,
  type InterviewAgentMemoryEventItem,
  type InterviewAgentToolCallItem,
  type InterviewAgentTraceItem,
  type InterviewSessionItem
} from '@/api/modules/interview';
import { useExport } from '@/composables/useExport';
import { Download, UserFilled, Opportunity, ChatDotRound } from '@element-plus/icons-vue';
import { ElMessage, ElRow, ElCol, ElDivider, ElTable, ElTableColumn, ElRate, ElTag, ElTimeline, ElTimelineItem, ElCollapse, ElCollapseItem, ElButton, ElAvatar, ElIcon, type CollapseModelValue } from 'element-plus';

const route = useRoute();
const EmotionChart = defineAsyncComponent(() => import('@/components/common/EmotionChart.vue'));
const AbilityRadarChart = defineAsyncComponent(() => import('@/components/common/AbilityRadarChart.vue'));
const MarkdownRenderer = defineAsyncComponent(() => import('@/components/common/MarkdownRenderer.vue'));

const isLoading = ref(true);
const reportData = ref<InterviewReport | null>(null);
const sessionInfo = ref<InterviewSessionItem | null>(null);
const agentTraces = ref<InterviewAgentTraceItem[]>([]);
const agentToolCalls = ref<InterviewAgentToolCallItem[]>([]);
const agentMemoryEvents = ref<InterviewAgentMemoryEventItem[]>([]);
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

const stageLabel = (stage?: string) => {
  const labels: Record<string, string> = {
    opening: '开场',
    resume_deep_dive: '简历深挖',
    technical_deep_dive: '技术深挖',
    behavioral: '行为面试',
    wrap_up: '收尾',
  };
  return stage ? labels[stage] || stage : '未记录';
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
    try {
      const [traces, toolCalls, memoryEvents] = await Promise.all([
        getInterviewAgentTracesApi(sessionId),
        getInterviewAgentToolCallsApi(sessionId),
        getInterviewAgentMemoryEventsApi(sessionId),
      ]);
      agentTraces.value = traces;
      agentToolCalls.value = toolCalls;
      agentMemoryEvents.value = memoryEvents;
    } catch (error) {
      agentTraces.value = [];
      agentToolCalls.value = [];
      agentMemoryEvents.value = [];
      console.warn('加载 Agent 审计数据失败', error);
    }

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

const hasVerificationChain = computed(() => {
  return Boolean(reportData.value?.verified_abilities?.length || reportData.value?.unverified_risks?.length);
});

const qualityBreakdownWithQuestion = computed(() => {
  if (!reportData.value?.question_quality_breakdown || !sessionInfo.value?.questions) {
    return [];
  }
  return reportData.value.question_quality_breakdown.map(item => {
    const question = sessionInfo.value?.questions.find(q => q.sequence === item.question_sequence);
    return {
      ...item,
      question_text: question?.question_text || `问题 ${item.question_sequence}`
    };
  });
});

const compactJson = (value?: Record<string, any>) => {
  if (!value || !Object.keys(value).length) return '无';
  const text = JSON.stringify(value);
  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
};

const environmentRiskLabel = (flag: string) => {
  const labels: Record<string, string> = {
    no_visual_frames: '无视觉帧',
    weak_visual_signal: '视觉信号弱',
    low_asr_confidence: 'ASR置信度低',
    asr_confidence_missing: 'ASR置信度缺失',
  };
  return labels[flag] || flag;
};

const signalQualityLabel = (quality?: string) => {
  const labels: Record<string, string> = {
    normal: '正常',
    limited: '有限',
    needs_confirmation: '需确认',
  };
  return quality ? labels[quality] || quality : '未记录';
};

const visualSignalLabel = (quality?: string) => {
  const labels: Record<string, string> = {
    normal: '正常',
    weak: '偏弱',
    unavailable: '不可用',
  };
  return quality ? labels[quality] || quality : '未记录';
};

const suggestedActionLabel = (action?: string) => {
  const labels: Record<string, string> = {
    continue: '继续面试',
    confirm_transcript_before_deepening: '先确认转写再深挖',
    ask_candidate_to_confirm_transcript: '请候选人确认转写',
    ignore_visual_signal: '忽略视觉信号',
  };
  return action ? labels[action] || action : '未记录建议动作';
};

const environmentAuditRows = computed(() => {
  return agentTraces.value
    .map(trace => {
      const question = sessionInfo.value?.questions?.find(item => item.id === trace.question);
      const environmentContext = trace.output_summary?.environment_context
        || trace.node_outputs?.summarize_environment_context
        || {};
      const environmentPolicy = trace.question_plan?.environment_policy
        || trace.node_outputs?.plan_next_question?.environment_policy
        || {};
      const riskFlags = environmentContext.risk_flags || environmentPolicy.risk_flags || [];
      const hasEnvironmentData = Object.keys(environmentContext).length || Object.keys(environmentPolicy).length;
      if (!hasEnvironmentData) return null;
      const confidence = environmentContext.asr_confidence;
      return {
        sequenceLabel: question ? `Q${question.sequence}` : '-',
        frame_count: environmentContext.frame_count ?? 0,
        has_audio: Boolean(environmentContext.has_audio),
        asrConfidenceText: confidence === null || confidence === undefined ? '未记录' : Number(confidence).toFixed(2),
        signalQualityLabel: signalQualityLabel(environmentContext.signal_quality),
        visualSignalLabel: visualSignalLabel(environmentContext.visual_signal_quality),
        suggestedActionLabel: suggestedActionLabel(environmentContext.suggested_action || environmentPolicy.suggested_action),
        risk_flags: Array.isArray(riskFlags) ? riskFlags : [],
        use_for_scoring: Boolean(environmentContext.use_for_scoring || environmentPolicy.use_for_scoring),
        scoringPolicyText: environmentContext.scoring_policy || '环境信号仅用于恢复、确认和追问策略',
      };
    })
    .filter(Boolean) as Array<Record<string, any>>;
});

const agentTraceRows = computed(() => {
  if (!agentTraces.value.length) return [];
  return agentTraces.value.map(trace => {
    const question = sessionInfo.value?.questions?.find(item => item.id === trace.question);
    const nodeOrder = trace.output_summary?.node_order || Object.keys(trace.node_outputs || {});
    const retrievalTrace = trace.node_outputs?.retrieve_knowledge?.retrieval_trace || {};
    const toolCalls = trace.output_summary?.tool_calls || [];
    const firstTool = Array.isArray(toolCalls) ? toolCalls[0] : null;
    const sourceCount = trace.node_outputs?.retrieve_knowledge?.source_count ?? firstTool?.output_summary?.source_count ?? 0;
    const planTarget = trace.question_plan?.target || trace.node_outputs?.plan_next_question?.target || '';
    const validationErrors = trace.validation_errors || trace.node_outputs?.validate_question?.validation_errors || [];
    return {
      ...trace,
      sequenceLabel: question ? `Q${question.sequence}` : '-',
      nodeOrder,
      planTarget,
      validationText: Array.isArray(validationErrors) ? validationErrors.join(', ') : '',
      toolSummary: firstTool
        ? `${firstTool.name || 'tool'}：${firstTool.ok ? '命中' : '未命中'}，来源 ${sourceCount}`
        : `知识检索来源 ${sourceCount}`,
      retrievalSummary: [
        `vector ${retrievalTrace.vector_count ?? 0}`,
        `keyword ${retrievalTrace.keyword_count ?? 0}`,
        `RRF ${retrievalTrace.rrf_count ?? 0}`,
        `filtered ${retrievalTrace.filtered_count ?? 0}`,
        `rerank ${retrievalTrace.rerank_used ? 'yes' : 'no'}`,
      ].join(' / '),
    };
  });
});

const agentToolCallRows = computed(() => {
  return agentToolCalls.value.map(call => {
    const question = sessionInfo.value?.questions?.find(item => item.id === call.question);
    const retrievalTrace = call.retrieval_trace || {};
    return {
      ...call,
      sequenceLabel: question ? `Q${question.sequence}` : '-',
      statusLabel: call.status === 'success' ? '成功' : call.status === 'degraded' ? '降级' : '失败',
      outputText: compactJson(call.output_summary),
      retrievalSummary: [
        `vector ${retrievalTrace.vector_count ?? 0}`,
        `keyword ${retrievalTrace.keyword_count ?? 0}`,
        `RRF ${retrievalTrace.rrf_count ?? 0}`,
        `filtered ${retrievalTrace.filtered_count ?? 0}`,
        `rerank ${retrievalTrace.rerank_used ? 'yes' : 'no'}`,
      ].join(' / '),
    };
  });
});

const agentMemoryEventRows = computed(() => {
  return agentMemoryEvents.value.map(event => {
    const question = sessionInfo.value?.questions?.find(item => item.id === event.question);
    return {
      ...event,
      sequenceLabel: question ? `Q${question.sequence}` : '-',
      valueText: compactJson(event.value_summary),
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

.verification-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.verification-card .report-card__body {
  min-height: 110px;
}

.evaluation-snapshot {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.evaluation-snapshot div {
  padding: 14px;
  border-radius: 18px;
  background: #f6f9fe;
  border: 1px solid #e3ecf8;
}

.evaluation-snapshot span {
  display: block;
  margin-bottom: 6px;
  color: #7a8aa2;
  font-size: 12px;
}

.evaluation-snapshot strong {
  color: #1d3150;
}

.snapshot-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.muted-copy {
  margin: 0;
  color: #7a8aa2;
}

.score-badge,
.mini-score {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  padding: 4px 9px;
  border-radius: 999px;
  color: #17634d;
  font-size: 12px;
  font-weight: 800;
  background: #daf8e8;
  border: 1px solid #9bdcb8;
}

.agent-trace-table :deep(.el-table__cell) {
  vertical-align: top;
}

.trace-stack {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: #31415d;
  line-height: 1.5;
}

.trace-stack small {
  color: #7b8aa2;
  line-height: 1.5;
}

.trace-node-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.audit-section + .audit-section {
  margin-top: 22px;
}

.audit-note {
  margin: 0 0 14px;
  padding: 10px 12px;
  border: 1px solid rgba(166, 202, 245, 0.72);
  border-radius: 14px;
  color: #395474;
  font-size: 13px;
  line-height: 1.7;
  background: rgba(238, 246, 255, 0.78);
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

.feedback-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.feedback-extra {
  margin: 8px 0 0;
  color: #4b6b5d;
  font-size: 13px;
  line-height: 1.6;
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

  .verification-grid {
    grid-template-columns: 1fr;
  }

  .evaluation-snapshot {
    grid-template-columns: 1fr;
  }

  .hero-main h2 {
    font-size: 28px;
  }
}
</style>
