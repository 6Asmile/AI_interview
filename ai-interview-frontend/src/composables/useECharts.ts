// src/composables/useECharts.ts
import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue';
import * as echarts from 'echarts/core';
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components';
import { LineChart } from 'echarts/charts';
import { UniversalTransition } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';

// 注册 ECharts 组件
echarts.use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
  LineChart,
  CanvasRenderer,
  UniversalTransition
]);

export function useECharts(
  elementRef: Ref<HTMLElement | null>,
  options: Ref<EChartsOption>
) {
  const chartInstance = ref<echarts.ECharts | null>(null);

  const initChart = () => {
    if (elementRef.value && !chartInstance.value) {
      chartInstance.value = echarts.init(elementRef.value);
    }
    if (chartInstance.value) {
      chartInstance.value.setOption(options.value);
    }
  };

  const resizeChart = () => {
    chartInstance.value?.resize();
  };

  onMounted(() => {
    initChart();
    window.addEventListener('resize', resizeChart);
  });

  onUnmounted(() => {
    chartInstance.value?.dispose();
    window.removeEventListener('resize', resizeChart);
  });

  // 监听图表配置项的变化，并重新渲染
  watch(options, (newOptions) => {
    if (chartInstance.value) {
      chartInstance.value.setOption(newOptions);
    }
  }, { deep: true });

  return {
    chartInstance,
  };
}