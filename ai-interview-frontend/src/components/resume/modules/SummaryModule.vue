<!-- src/components/resume/modules/SummaryModule.vue -->
<template>
  <div class="summary-module section-module">
    <h3 class="section-title">{{ title }}</h3>
    <pre class="section-content">{{ summary }}</pre>
  </div>
</template>

<script setup lang="ts">
defineProps({
  title: { type: String, default: '个人总结' },
  summary: { type: String, default: '' }
});
</script>

<style scoped>
/* 提取公共样式，可以在 global.css 中定义 */
.section-module .section-title {
  font-size: 18px;
  font-weight: 600;
  border-bottom: 2px solid #333;
  padding-bottom: 6px;
  margin-bottom: 12px;
}
.section-module .section-content {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  white-space: pre-wrap;
  font-family: inherit;
}
</style>