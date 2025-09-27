<template>
  <div class="settings-panel-wrapper">
    <InfoPanel />
    <EducationPanel />
    <WorkExperiencePanel />
    <!-- 【新增】加载新模块 -->
    <ProjectExperiencePanel />
    <SkillsPanel />
  </div>
</template>

<script setup lang="ts">
import InfoPanel from './InfoPanel.vue';
import EducationPanel from './EducationPanel.vue';
import WorkExperiencePanel from './WorkExperiencePanel.vue';
// 【新增】导入新模块
import ProjectExperiencePanel from './ProjectExperiencePanel.vue';
import SkillsPanel from './SkillsPanel.vue';
</script>

<style scoped>
.settings-panel-wrapper {
  padding: 20px;
}
</style>