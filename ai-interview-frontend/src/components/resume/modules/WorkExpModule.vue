<!-- src/components/resume/modules/WorkExpModule.vue -->
<template>
  <div class="work-exp-module section-module">
    <h3 class="section-title">{{ title }}</h3>
    <div v-for="exp in experiences" :key="exp.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ exp.company }}</span>
        <span class="sub-info">{{ exp.position }}</span>
        <span class="date-range">{{ exp.dateRange }}</span>
      </div>
      <pre class="description">{{ exp.description }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Experience {
  id: string;
  company: string;
  position: string;
  dateRange: string;
  description: string;
}
defineProps({
  title: { type: String, default: '工作经历' },
  experiences: { type: Array as () => Experience[], default: () => [] }
});
</script>

<style scoped>
/* 使用与教育背景类似的样式 */
.section-title { font-size: 18px; font-weight: 600; border-bottom: 2px solid #333; padding-bottom: 6px; margin-bottom: 12px; }
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.main-info { font-weight: 600; }
.sub-info { color: #555; }
.date-range { font-style: italic; color: #888; }
.description { font-size: 14px; color: #555; line-height: 1.8; white-space: pre-wrap; font-family: inherit; }
</style>