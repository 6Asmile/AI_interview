<template>
  <div ref="chartRef" style="width: 100%; height: 250px;"></div>
</template>

<script setup lang="ts">
// [核心修正] 显式导入 Ref 类型，以提供更强的类型提示
import { ref, onMounted, watch, type Ref } from 'vue';
import { useECharts } from '@/composables/useECharts';
import type { EChartsOption } from 'echarts';
import type { AnalysisFrame } from '@/api/modules/interview';

const props = defineProps<{
  analysisData: AnalysisFrame[];
}>();

const chartRef = ref<HTMLElement | null>(null);

const emotionMap: Record<string, string> = {
  neutral: '平静', happy: '开心', sad: '悲伤', angry: '生气',
  fearful: '害怕', disgusted: '厌恶', surprised: '惊讶',
};

// [核心修正] 将 options 的类型显式声明为 Ref<EChartsOption>
const options: Ref<EChartsOption> = ref({
  title: { text: '图表加载中...', left: 'center', top: 'center' }
});

const updateChartOptions = () => {
  if (!props.analysisData || props.analysisData.length === 0) {
    options.value = { title: { text: '无情绪数据', left: 'center', top: 'center' }};
    return;
  }

  const timestamps = props.analysisData.map(d => d.timestamp);
  const startTime = timestamps[0];
  const seriesData: any[] = [];
  const legendData: string[] = [];
  
  const emotionsToShow = Object.keys(emotionMap);

  emotionsToShow.forEach(emotionKey => {
    legendData.push(emotionMap[emotionKey]);
    seriesData.push({
      name: emotionMap[emotionKey],
      type: 'line',
      smooth: true,
      data: props.analysisData.map(frame => [
        (frame.timestamp - startTime) / 1000,
        Math.round((frame.emotions[emotionKey] || 0) * 100)
      ])
    });
  });

  options.value = {
    tooltip: { trigger: 'axis' },
    legend: { data: legendData, bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: {
      type: 'value',
      name: '时间 (秒)',
      axisLabel: { formatter: '{value} s' }
    },
    yAxis: {
      type: 'value',
      name: '置信度 (%)',
      min: 0,
      max: 100
    },
    series: seriesData
  };
};

onMounted(updateChartOptions);
watch(() => props.analysisData, updateChartOptions, { deep: true });

useECharts(chartRef, options);

</script>