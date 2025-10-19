<!-- src/components/resume/modules/WorkExpModule.vue -->
<template>
  <div class="work-exp-module">
    <component :is="titleComponent" :text="title" />
    <div v-for="exp in experiences" :key="exp.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ exp.company }}</span>
        <span class="sub-info">{{ exp.position }}</span>
        <span class="date-range">{{ formatDisplayDateRange(exp.dateRange) }}</span>
      </div>
      <!-- 【核心修改】 -->
      <div class="description" v-html="exp.description"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';
import SectionTitleStyle4 from './common/SectionTitleStyle4.vue';

interface Experience {
  id: string;
  company: string;
  position: string;
  dateRange: (string | null)[];
  description: string;
}

const props = defineProps({
  title: { type: String, default: '工作经历' },
  titleStyle: { type: String, default: 'style1' },
  experiences: { type: Array as () => Experience[], default: () => [] }
});

const titleComponent = computed(() => {
  if (props.titleStyle === 'style2') return markRaw(SectionTitleStyle2);
  if (props.titleStyle === 'style3') return markRaw(SectionTitleStyle3);
  if (props.titleStyle === 'style4') return markRaw(SectionTitleStyle4);
  return markRaw(SectionTitle);
});

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

/* 【核心修改】 */
.description {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  font-family: inherit;
}
.description :deep(p) { margin: 0; }
.description :deep(ul), .description :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
</style>