<!-- src/components/resume/modules/SkillsModule.vue -->
<template>
  <div class="skills-module section-module">
    <h3 class="section-title">{{ title }}</h3>
    <ul class="skills-list">
      <li v-for="skill in skills" :key="skill.id">
        <span class="skill-name">{{ skill.name }}:</span>
        <span class="skill-proficiency">{{ skill.proficiency }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
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
.section-title { font-size: 18px; font-weight: 600; border-bottom: 2px solid #333; padding-bottom: 6px; margin-bottom: 12px; }
.skills-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 8px 24px;
  list-style: none;
  padding: 0;
}
.skill-name { font-weight: 500; }
.skill-proficiency { color: #555; }
</style>