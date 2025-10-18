<!-- src/components/resume/modules/SkillsModule.vue -->
<template>
  <div class="skills-module">
    <component :is="titleComponent" :text="title" />
    <ul class="skills-list">
      <li v-for="skill in skills" :key="skill.id">
        <span class="skill-name">{{ skill.name }}:</span>
        <span class="skill-proficiency">{{ skill.proficiency }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';

interface Skill {
  id: string;
  name: string;
  proficiency: string;
}

const props = defineProps({
  title: { type: String, default: '专业技能' },
  titleStyle: { type: String, default: 'style1' },
  skills: { type: Array as () => Skill[], default: () => [] }
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