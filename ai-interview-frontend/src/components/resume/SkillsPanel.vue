<template>
  <SectionCard title="专业技能">
    <div v-for="(skill, index) in store.resumeData.skills" :key="index" class="skill-item">
      <el-input v-model="skill.skill_name" placeholder="技能名称，如 Java" />
      <el-input v-model="skill.proficiency" placeholder="熟练度，如 精通" />
      <el-button type="danger" :icon="Delete" circle @click="store.removeSkill(index)" />
    </div>
    <el-button type="primary" link @click="store.addSkill">+ 添加技能</el-button>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from '@/components/common/SectionCard.vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { Delete } from '@element-plus/icons-vue';
const store = useResumeEditorStore();
</script>

<style scoped>
.skill-item {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
</style>