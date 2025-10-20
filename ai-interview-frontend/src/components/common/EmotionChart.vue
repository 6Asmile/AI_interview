<template>
  <div ref="chartRef" style="width: 100%; height: 250px;"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, type Ref, defineExpose } from 'vue';
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

const options: Ref<EChartsOption> = ref({
  title: { text: '', left: 'center', top: 'center' }
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
        (frame.timestamp - startTime) / 1000, // X轴：秒
        Math.round((frame.emotions[emotionKey] || 0) * 100) // Y轴：百分比
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

// [核心修正 1/2] 从 useECharts 中获取 chartInstance
const { chartInstance } = useECharts(chartRef, options);

// [核心修正 2/2] 定义 resize 方法并暴露给父组件
const resizeChart = () => {
  chartInstance.value?.resize();
};

defineExpose({
  resizeChart
});

</script>