<template>
  <div ref="chartRef" style="width: 100%; height: 350px;"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, type Ref } from 'vue';
import { useECharts } from '@/composables/useECharts';
import type { EChartsOption } from 'echarts';
import * as echarts from 'echarts/core';
import { RadarChart } from 'echarts/charts';
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components';

// 注册雷达图所需的组件
echarts.use([RadarChart, LegendComponent, TitleComponent, TooltipComponent]);

interface AbilityScore {
  name: string;
  score: number;
}

const props = defineProps<{
  abilityScores: AbilityScore[];
}>();

const chartRef = ref<HTMLElement | null>(null);
const options: Ref<EChartsOption> = ref({
  title: { text: '能力维度雷达图' }
});

const updateChartOptions = () => {
  if (!props.abilityScores || props.abilityScores.length === 0) {
    options.value = { title: { text: '无能力数据', left: 'center', top: 'center' }};
    return;
  }

  const indicatorData = props.abilityScores.map(item => ({
    name: item.name,
    max: 5 // 最高分为 5
  }));
  
  const seriesValue = props.abilityScores.map(item => item.score);

  options.value = {
    tooltip: {
      trigger: 'item'
    },
    legend: {
      data: ['能力评估'],
      bottom: 5,
    },
    radar: {
      indicator: indicatorData,
      radius: '60%',
      axisName: {
        color: '#333',
        fontSize: 12
      }
    },
    series: [
      {
        name: '能力评估',
        type: 'radar',
        data: [
          {
            value: seriesValue,
            name: '能力评估',
            areaStyle: {
              color: 'rgba(64, 158, 255, 0.4)'
            },
            lineStyle: {
              color: 'rgba(64, 158, 255, 1)'
            },
            itemStyle: {
              color: 'rgba(64, 158, 255, 1)'
            }
          }
        ]
      }
    ]
  };
};

onMounted(updateChartOptions);
watch(() => props.abilityScores, updateChartOptions, { deep: true });

useECharts(chartRef, options);
</script>