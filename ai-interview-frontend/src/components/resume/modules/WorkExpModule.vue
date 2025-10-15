<!-- src/components/resume/modules/WorkExpModule.vue -->
<template>
  <div class="work-exp-module">
    <SectionTitle :text="title" />
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
import SectionTitle from './common/SectionTitle.vue';

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
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
.main-info { font-weight: 600; }
.sub-info { color: #555; }
.date-range { font-style: italic; color: #888; }
.description { font-size: 14px; color: #555; line-height: 1.8; white-space: pre-wrap; font-family: inherit; }
</style>