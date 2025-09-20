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
        <el-row :gutter="20">
          <el-col :span="12">
            <div ref="radarChart" style="width: 100%; height: 400px;"></div>
          </el-col>
          <el-col :span="12" class="ability-bars">
             <div v-for="ability in reportData.ability_scores" :key="ability.name" class="ability-item">
               <span>{{ ability.name }}</span>
               <el-progress :percentage="ability.score * 20" :format="() => `${ability.score} 分`" />
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
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <el-skeleton :rows="10" animated v-if="loading" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import * as echarts from 'echarts';
import { getInterviewReportApi, type InterviewReport } from '@/api/modules/report';
import { getInterviewSessionApi, type InterviewSessionItem } from '@/api/modules/interview';
import { Document, Opportunity } from '@element-plus/icons-vue';

const route = useRoute();
const loading = ref(true);
const reportData = ref<InterviewReport | null>(null);
const sessionInfo = ref<InterviewSessionItem | null>(null);
const radarChart = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null; // 用于存储 ECharts 实例

const fetchData = async (sessionId: string) => {
  loading.value = true;
  try {
    const [report, session] = await Promise.all([
      getInterviewReportApi(sessionId),
      getInterviewSessionApi(sessionId),
    ]);
    reportData.value = report;
    sessionInfo.value = session;
    
    // 【核心修正 #1】使用 setTimeout 延迟初始化
    setTimeout(() => {
      initRadarChart();
    }, 100); // 延迟 100 毫秒，足以让 DOM 完成布局

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
  // 组件卸载时销毁图表实例，防止内存泄漏
  if (chartInstance) {
    chartInstance.dispose();
  }
});

const initRadarChart = () => {
  // 【核心修正 #2】增强数据校验
  if (!radarChart.value || !reportData.value || !reportData.value.ability_scores || reportData.value.ability_scores.length === 0) {
    console.warn("无法初始化雷达图，缺少 ability_scores 数据。");
    if(radarChart.value) radarChart.value.innerHTML = '<div class="chart-error">AI 未返回能力维度评分数据</div>';
    return;
  }
  
  chartInstance = echarts.init(radarChart.value);
  
  const indicatorData = reportData.value.ability_scores.map(item => ({
    name: item.name,
    max: 5,
  }));
  
  const seriesData = reportData.value.ability_scores.map(item => {
    const score = Number(item.score);
    return isNaN(score) ? 0 : score;
  });

  const option = {
    tooltip: { trigger: 'item' },
    radar: {
      indicator: indicatorData,
      radius: '65%',
      center: ['50%', '55%'],
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: seriesData,
            name: '能力评估',
            areaStyle: { color: 'rgba(64, 158, 255, 0.4)' }
          }
        ]
      }
    ]
  };
  chartInstance.setOption(option);

  // 【核心修正 #3】增加 resize 监听
  const resizeObserver = new ResizeObserver(() => {
    chartInstance?.resize();
  });
  resizeObserver.observe(radarChart.value);
};
</script>

<style scoped>
/* --- 样式保持不变，只为新元素追加样式 --- */
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
/* 新增样式 */
.chart-error {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: #909399;
  font-size: 14px;
}
</style>