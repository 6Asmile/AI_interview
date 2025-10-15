<!-- src/components/resume/modules/SkillsModule.vue -->
<template>
  <div class="skills-module">
    <SectionTitle :text="title" />
    <ul class="skills-list">
      <li v-for="skill in skills" :key="skill.id">
        <span class="skill-name">{{ skill.name }}:</span>
        <span class="skill-proficiency">{{ skill.proficiency }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import SectionTitle from './common/SectionTitle.vue';

interface Skill {
  id: string;
  name: string;
  proficiency: string;
}
defineProps({
  title: { type: String, default: '专业技能' },
  skills: { type: Array as () => Skill[], default: () => [] }
});
</script>

<style scoped>
.skills-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 8px 24px;
  list-style: none;
  padding: 0;
  font-size: 14px;
}
.skill-name { font-weight: 500; }
.skill-proficiency { color: #555; }
</style>