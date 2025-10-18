<!-- src/components/resume/modules/SummaryModule.vue -->
<template>
  <div class="summary-module">
    <component :is="titleComponent" :text="title" />
    <pre class="section-content">{{ summary }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';

const props = defineProps({
  title: { type: String, default: '自我评价' },
  titleStyle: { type: String, default: 'style1' },
  summary: { type: String, default: '' }
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
</script>

<style scoped>
.section-content {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  white-space: pre-wrap;
  font-family: inherit;
}
</style>