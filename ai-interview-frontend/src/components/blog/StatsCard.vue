<template>
  <el-card shadow="hover" class="stats-card">
    <div class="stats-content">
      <el-icon :size="40" class="stats-icon"><component :is="icon" /></el-icon>
      <div class="stats-text">
        <div class="stats-value">{{ value }}</div>
        <div class="stats-label">{{ label }}</div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { defineProps, type Component } from 'vue';
import { ElCard, ElIcon } from 'element-plus';

defineProps<{
  icon: Component;
  value: number;
  label: string;
}>();
</script>

<style scoped>
.stats-card {
  border-radius: 8px;
}
.stats-content {
  display: flex;
  align-items: center;
}
.stats-icon {
  color: var(--el-color-primary);
  margin-right: 16px;
}
.stats-text {
  display: flex;
  flex-direction: column;
}
.stats-value {
  font-size: 24px;
  font-weight: bold;
}
.stats-label {
  font-size: 14px;
  color: #909399;
}
</style>