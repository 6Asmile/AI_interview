<!-- src/components/resume/modules/ProjectModule.vue -->
<template>
  <div class="project-module section-module">
    <h3 class="section-title">{{ title }}</h3>
    <div v-for="proj in projects" :key="proj.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ proj.name }}</span>
        <span class="sub-info">{{ proj.role }}</span>
        <span class="date-range">{{ proj.dateRange }}</span>
      </div>
      <p class="tech-stack" v-if="proj.techStack"><b>技术栈:</b> {{ proj.techStack }}</p>
      <pre class="description">{{ proj.description }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Project {
  id: string;
  name: string;
  role: string;
  dateRange: string;
  description: string;
  techStack: string;
  projectUrl: string;
}
defineProps({
  title: { type: String, default: '项目经历' },
  projects: { type: Array as () => Project[], default: () => [] }
});
</script>

<style scoped>
.section-title { font-size: 18px; font-weight: 600; border-bottom: 2px solid #333; padding-bottom: 6px; margin-bottom: 12px; }
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.main-info { font-weight: 600; }
.sub-info { color: #555; }
.date-range { font-style: italic; color: #888; }
.tech-stack { font-size: 14px; color: #555; margin-bottom: 4px; }
.description { font-size: 14px; color: #555; line-height: 1.8; white-space: pre-wrap; font-family: inherit; }
</style>