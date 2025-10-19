<!-- src/components/resume/modules/EducationModule.vue -->
<template>
  <div class="education-module">
    <component :is="titleComponent" :text="title" />
    <div v-for="edu in educations" :key="edu.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ edu.school }}</span>
        <span class="sub-info">{{ edu.major }} - {{ edu.degree }}</span>
        <span class="date-range">{{ formatDisplayDateRange(edu.dateRange) }}</span>
      </div>
      <!-- 【核心修改】 -->
      <div v-if="edu.description" class="description" v-html="edu.description"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';
import SectionTitleStyle4 from './common/SectionTitleStyle4.vue';

interface Education {
  id: string;
  school: string;
  major: string;
  degree: string;
  dateRange: (string | null)[];
  description: string;
}

const props = defineProps({
  title: { type: String, default: '教育背景' },
  titleStyle: { type: String, default: 'style1' },
  educations: { type: Array as () => Education[], default: () => [] }
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
  margin-left: 8px;
}
.description :deep(p) { margin: 0; }
.description :deep(ul), .description :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
</style>