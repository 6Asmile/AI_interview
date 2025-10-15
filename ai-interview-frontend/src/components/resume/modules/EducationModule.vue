<!-- src/components/resume/modules/EducationModule.vue -->
<template>
  <div class="education-module">
    <SectionTitle :text="title" />
    <div v-for="edu in educations" :key="edu.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ edu.school }}</span>
        <span class="sub-info">{{ edu.major }} - {{ edu.degree }}</span>
        <span class="date-range">{{ edu.dateRange }}</span>
      </div>
      <pre v-if="edu.description" class="description">{{ edu.description }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import SectionTitle from './common/SectionTitle.vue';

interface Education {
  id: string;
  school: string;
  major: string;
  degree: string;
  dateRange: string;
  description: string;
}
defineProps({
  title: { type: String, default: '教育背景' },
  educations: { type: Array as () => Education[], default: () => [] }
});
</script>

<style scoped>
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
.main-info { font-weight: 600; }
.sub-info { color: #555; }
.date-range { font-style: italic; color: #888; }
.description { font-size: 14px; color: #555; line-height: 1.8; white-space: pre-wrap; font-family: inherit; margin-left: 8px; }
</style>