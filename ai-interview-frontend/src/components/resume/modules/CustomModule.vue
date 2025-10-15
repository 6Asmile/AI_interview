<!-- src/components/resume/modules/CustomModule.vue -->
<template>
  <div class="custom-module">
    <SectionTitle :text="title" />
    <pre class="section-content">{{ content }}</pre>
  </div>
</template>

<script setup lang="ts">
import SectionTitle from './common/SectionTitle.vue';

defineProps({
  title: { type: String, default: '自定义标题' },
  content: { type: String, default: '' }
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