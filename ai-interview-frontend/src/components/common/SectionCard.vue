<!-- src/components/common/SectionCard.vue -->
<template>
  <div class="resume-section">
    <div class="section-header">
      <h3>{{ title }}</h3>
      <el-button type="primary" :icon="Plus" circle @click="$emit('add')" />
    </div>
    <div class="section-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
defineProps<{
  title: string;
}>();
defineEmits(['add']);
</script>

<style scoped>
.resume-section {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
h3 {
  margin: 0;
}
</style>