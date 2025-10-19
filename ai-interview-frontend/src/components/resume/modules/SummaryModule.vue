<!-- src/components/resume/modules/SummaryModule.vue -->
<template>
  <div class="summary-module">
    <component :is="titleComponent" :text="title" />
    <!-- 【核心修改】 -->
    <div class="section-content" v-html="summary"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';
import SectionTitleStyle4 from './common/SectionTitleStyle4.vue';

const props = defineProps({
  title: { type: String, default: '自我评价' },
  titleStyle: { type: String, default: 'style1' },
  summary: { type: String, default: '' }
});

const titleComponent = computed(() => {
  if (props.titleStyle === 'style2') return markRaw(SectionTitleStyle2);
  if (props.titleStyle === 'style3') return markRaw(SectionTitleStyle3);
  if (props.titleStyle === 'style4') return markRaw(SectionTitleStyle4);
  return markRaw(SectionTitle);
});
</script>

<style scoped>
/* 【核心修改】 */
.section-content {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  font-family: inherit;
}
.section-content :deep(p) { margin: 0; }
.section-content :deep(ul), .section-content :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
</style>