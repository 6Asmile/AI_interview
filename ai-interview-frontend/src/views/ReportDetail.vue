<template>
  <div class="page-container report-container">
    <el-card v-if="reportData && !loading" class="report-card">
      <template #header>
        <div class="page-card-header report-header">
          <div class="header-left">
            <el-icon :size="30"><Document /></el-icon>
            <h1>AI 面试评估报告</h1>
          </div>
          <div class="header-right">
            <span>面试用户: {{ sessionInfo?.user?.username || 'N/A' }}</span>
            <span>面试时间: {{ sessionInfo?.started_at ? new Date(sessionInfo.started_at).toLocaleString() : 'N/A' }}</span>
          </div>
        </div>
      </template>
      
      <div class="section">
        <h2>综合评语</h2>
        <div class="overall-comment">
          <el-icon><Opportunity /></el-icon>
          <p>{{ reportData.overall_comment }}</p>
        </div>
      </div>
      
      <div class="section">
        <h2>能力维度分析</h2>
        <el-row :gutter="40">
          <el-col :span="12">
            <div ref="radarChart" style="width: 100%; height: 400px;"></div>
          </el-col>
          <el-col :span="12" class="ability-bars">
             <div v-for="ability in reportData.ability_scores" :key="ability.name" class="ability-item">
               <span>{{ ability.name }}</span>
               <el-progress :percentage="ability.score * 20" :format="() => `${ability.score} / 5`" />
             </div>
          </el-col>
        </el-row>
      </div>

      <el-row :gutter="20">
        <el-col :span="12">
          <div class="section">
            <h2>亮点表现</h2>
            <div class="suggestion-box good">
              <p>{{ reportData.strength_analysis }}</p>
            </div>
          </div>
        </el-col>
        <el-col :span="12">
          <div class="section">
            <h2>待改进点</h2>
             <div class="suggestion-box bad">
              <p>{{ reportData.weakness_analysis }}</p>
            </div>
          </div>
        </el-col>
      </el-row>
      
      <div class="section">
        <h2>改进建议</h2>
        <div v-for="(suggestion, index) in reportData.improvement_suggestions" :key="index" class="suggestion-item">
          <el-tag type="success" effect="plain" round class="suggestion-index">{{ index + 1 }}</el-tag>
          <p>{{ suggestion }}</p>
        </div>
      </div>
      
      <!-- 新增：关键词分析模块 -->
      <div class="section">
        <h2>关键词分析</h2>
        <el-row :gutter="20">
          <el-col :span="12">
            <p class="analysis-subtitle">匹配的关键词</p>
            <el-tag v-for="kw in reportData.keyword_analysis.matched_keywords" :key="kw" type="success" class="keyword-tag">{{ kw }}</el-tag>
            <el-empty v-if="!reportData.keyword_analysis.matched_keywords?.length" description="无" :image-size="50" />
          </el-col>
          <el-col :span="12">
            <p class="analysis-subtitle">建议补充的关键词</p>
            <el-tag v-for="kw in reportData.keyword_analysis.missing_keywords" :key="kw" type="warning" class="keyword-tag">{{ kw }}</el-tag>
            <el-empty v-if="!reportData.keyword_analysis.missing_keywords?.length" description="无" :image-size="50" />
          </el-col>
        </el-row>
        <div class="analysis-comment">
          <p>{{ reportData.keyword_analysis.analysis_comment }}</p>
        </div>
      </div>
      
      <!-- 新增：STAR 法则分析模块 -->
      <div class="section">
        <h2>STAR 法则分析</h2>
        <el-table :data="starAnalysisData" style="width: 100%">
          <el-table-column prop="question" label="行为问题" />
          <el-table-column prop="conforms_to_star" label="STAR 符合度" width="150" align="center">
            <template #default="scope">
              <el-tag :type="scope.row.conforms_to_star ? 'success' : 'danger'">
                {{ scope.row.conforms_to_star ? '符合' : '待改进' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="star_feedback" label="AI 反馈" />
        </el-table>
        <el-empty v-if="!starAnalysisData.length" description="本次面试未涉及需 STAR 法则作答的行为问题" />
      </div>
    </el-card>
    
    <el-card v-if="sessionInfo && !loading" class="review-card">
      <template #header>
        <div class="page-card-header">
          <h2>面试详情回顾</h2>
        </div>
      </template>
      <el-timeline>
        <el-timeline-item 
          v-for="(qa, index) in sessionInfo.questions" 
          :key="qa.id"
          :timestamp="`问题 ${index + 1}`"
          placement="top"
        >
          <el-card>
            <h4>{{ qa.question_text }}</h4>
            <p v-if="qa.answer_text" class="answer-text"><strong>您的回答:</strong> {{ qa.answer_text }}</p>
            <p v-if="qa.ai_feedback?.feedback" class="feedback-text">
              <strong>AI 简评:</strong> {{ qa.ai_feedback.feedback }}
            </p>
            <div v-if="qa.analysis_data && qa.analysis_data.length > 0" class="emotion-chart-container">
              <p class="chart-title">回答期间情绪波动</p>
              <div :ref="el => setChartRef(qa.id, el)" class="emotion-chart"></div>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <el-skeleton :rows="10" animated v-if="loading" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import { useRoute } from 'vue-router';
import * as echarts from 'echarts';
import { getInterviewReportApi, type InterviewReport } from '@/api/modules/report';
import { getInterviewSessionApi, type InterviewSessionItem, type AnalysisFrame } from '@/api/modules/interview';
import { Document, Opportunity } from '@element-plus/icons-vue';
import { emotionMap } from '@/composables/useFaceApi';

const route = useRoute();
const loading = ref(true);
const reportData = ref<InterviewReport | null>(null);
const sessionInfo = ref<InterviewSessionItem | null>(null);
const radarChart = ref<HTMLElement | null>(null);

const chartRefs = ref<Map<number, HTMLElement>>(new Map());
const chartInstances = new Map<number, echarts.ECharts>();
let radarChartInstance: echarts.ECharts | null = null;

const starAnalysisData = computed(() => {
  if (!reportData.value || !sessionInfo.value || !reportData.value.star_analysis) return [];
  return reportData.value.star_analysis
    .filter(sa => sa.is_behavioral_question)
    .map(sa => {
      const question = sessionInfo.value?.questions.find(q => q.sequence === sa.question_sequence);
      return {
        ...sa,
        question: question ? `Q${sa.question_sequence}: ${question.question_text}` : `问题 ${sa.question_sequence}`
      }
    });
});

const setChartRef = (id: number, el: any) => {
  if (el) { chartRefs.value.set(id, el); }
};

const fetchData = async (sessionId: string) => {
  loading.value = true;
  try {
    const [report, session] = await Promise.all([
      getInterviewReportApi(sessionId),
      getInterviewSessionApi(sessionId),
    ]);
    reportData.value = report;
    sessionInfo.value = session;
    
    setTimeout(() => {
      initRadarChart();
      initEmotionCharts();
    }, 200);
  } catch (error) {
    console.error("获取报告失败", error);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  const sessionId = route.params.id as string;
  if (sessionId) fetchData(sessionId);
});

onUnmounted(() => {
  radarChartInstance?.dispose();
  chartInstances.forEach(chart => chart.dispose());
});

const initRadarChart = () => {
  if (!radarChart.value || !reportData.value || !reportData.value.ability_scores || reportData.value.ability_scores.length === 0) {
    if(radarChart.value) radarChart.value.innerHTML = '<div class="chart-error">AI 未返回能力维度评分数据</div>';
    return;
  }
  
  if (!radarChartInstance) {
    radarChartInstance = echarts.init(radarChart.value);
  }
  
  const indicatorData = reportData.value.ability_scores.map(item => ({ name: item.name, max: 5 }));
  const seriesData = reportData.value.ability_scores.map(item => Number(item.score) || 0);

  const option = {
    tooltip: { trigger: 'item' },
    radar: { indicator: indicatorData, radius: '65%', center: ['50%', '55%'] },
    series: [{ type: 'radar', data: [{ value: seriesData, name: '能力评估', areaStyle: { color: 'rgba(64, 158, 255, 0.4)' }}] }]
  };
  radarChartInstance.setOption(option);
};

const initEmotionCharts = () => {
  if (!sessionInfo.value || !sessionInfo.value.questions) return;
  sessionInfo.value.questions.forEach(qa => {
    if (!qa.analysis_data || qa.analysis_data.length === 0) return;
    
    const chartDom = chartRefs.value.get(qa.id);
    if (chartDom) {
      let chart = chartInstances.get(qa.id);
      if (!chart) {
        chart = echarts.init(chartDom);
        chartInstances.set(qa.id, chart);
      }
      const timestamps = qa.analysis_data.map((d: AnalysisFrame) => (d.timestamp / 1000).toFixed(1) + 's');
      const series = Object.keys(emotionMap).map(key => ({
        name: emotionMap[key],
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: qa.analysis_data!.map((d: AnalysisFrame) => {
          const emotionValue = d.emotions ? d.emotions[key] : 0;
          return ((emotionValue || 0) * 100).toFixed(2);
        })
      }));
      const option = {
        tooltip: { trigger: 'axis' },
        legend: { data: Object.values(emotionMap), top: 'bottom', type: 'scroll' },
        grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: timestamps },
        yAxis: { type: 'value', max: 100, name: '置信度 (%)' },
        series: series
      };
      chart.setOption(option);
    }
  });
};
</script>

<style scoped>
.report-container { max-width: 1000px; margin: 20px auto; display: flex; flex-direction: column; gap: 20px;}
.report-header { align-items: center; }
.header-left { display: flex; align-items: center; gap: 10px; }
.header-left h1 { font-size: 1.8rem; margin: 0; }
.header-right { font-size: 0.9rem; color: #909399; display: flex; gap: 20px;}
.section { margin-top: 30px; }
.section h2 { font-size: 1.4rem; margin-bottom: 20px; border-left: 4px solid #409EFF; padding-left: 10px; }
.overall-comment { display: flex; gap: 10px; align-items: flex-start; background-color: #ecf5ff; padding: 15px; border-radius: 4px; color: #409eff; }
.overall-comment p { margin: 0; line-height: 1.6; }
.ability-bars { display: flex; flex-direction: column; justify-content: center; gap: 15px; padding: 10px 0; }
.ability-item { display: flex; align-items: center; gap: 15px; }
.ability-item span { width: 80px; text-align: right; }
.suggestion-box { padding: 15px; border-radius: 4px; line-height: 1.6; }
.suggestion-box.good { background-color: #f0f9eb; color: #67c23a; }
.suggestion-box.bad { background-color: #fef0f0; color: #f56c6c; }
.suggestion-item { display: flex; align-items: flex-start; gap: 10px; margin-top: 15px; }
.suggestion-index { font-weight: bold; }
.suggestion-item p { margin: 0; line-height: 1.6; }
.review-card { margin-top: 20px; }
.answer-text, .feedback-text { margin-top: 10px; padding: 10px; border-radius: 4px; line-height: 1.6; }
.answer-text { background-color: #f4f4f5; }
.feedback-text { background-color: #d9ecff; }
.emotion-chart-container { margin-top: 20px; border-top: 1px solid #f0f0f0; padding-top: 20px; }
.chart-title { font-weight: 500; color: #303133; margin-bottom: 10px; }
.emotion-chart { width: 100%; height: 300px; }
.chart-error { display: flex; justify-content: center; align-items: center; height: 100%; color: #909399; font-size: 14px; }
.analysis-subtitle { font-weight: bold; color: #606266; margin-bottom: 10px; }
.keyword-tag { margin: 5px; }
.analysis-comment { margin-top: 20px; padding: 15px; background-color: #f4f4f5; border-radius: 4px; font-size: 0.9rem; line-height: 1.6; }
</style>