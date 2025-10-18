<!-- src/components/resume/modules/WorkExpModule.vue -->
<template>
  <div class="work-exp-module">
    <!-- 【核心修改】使用动态组件来渲染标题 -->
    <component :is="titleComponent" :text="title" />

    <div v-for="exp in experiences" :key="exp.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ exp.company }}</span>
        <span class="sub-info">{{ exp.position }}</span>
        <span class="date-range">{{ formatDisplayDateRange(exp.dateRange) }}</span>
      </div>
      <pre class="description">{{ exp.description }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue'; // 导入新标题
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';

interface Experience {
  id: string;
  company: string;
  position: string;
  dateRange: (string | null)[];
  description: string;
}

const props = defineProps({
  title: { type: String, default: '工作经历' },
  // 【核心新增】接收一个 'titleStyle' prop
  titleStyle: { type: String, default: 'style1' }, // style1=深蓝块, style2=线条
  experiences: { type: Array as () => Experience[], default: () => [] }
});

// 【核心修改】扩展 computed 属性以支持 style3
const titleComponent = computed(() => {
  if (props.titleStyle === 'style2') {
    return markRaw(SectionTitleStyle2);
  }
  if (props.titleStyle === 'style3') {
    return markRaw(SectionTitleStyle3);
  }
  return markRaw(SectionTitle); // 默认返回 style1
});

// 日期格式化函数保持不变
const formatDisplayDateRange = (dateRange: (string | null)[] | string): string => {
  if (typeof dateRange === 'string') return dateRange;
  if (!Array.isArray(dateRange) || dateRange.length === 0) return '';
  const [start, end] = dateRange;
  const formattedStart = start ? start.replace('-', '.') : '';
  const formattedEnd = end ? end.replace('-', '.') : '至今';
  if (formattedStart && formattedEnd) return `${formattedStart} - ${formattedEnd}`;
  return formattedStart;
};
</script>

<style scoped>
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
.main-info { font-weight: 600; }
.sub-info { color: #555; }
.date-range { font-style: italic; color: #888; }
.description { font-size: 14px; color: #555; line-height: 1.8; white-space: pre-wrap; font-family: inherit; }
</style>