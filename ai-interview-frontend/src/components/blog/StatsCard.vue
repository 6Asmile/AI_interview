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
  border-radius: 22px;
  border: 1px solid rgba(207, 219, 238, 0.8);
  background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
  box-shadow: 0 18px 34px rgba(43, 67, 108, 0.08);
}
.stats-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stats-icon {
  color: var(--el-color-primary);
  width: 58px;
  height: 58px;
  border-radius: 18px;
  background: rgba(64, 158, 255, 0.1);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.stats-text {
  display: flex;
  flex-direction: column;
}
.stats-value {
  font-size: 28px;
  font-weight: bold;
  color: #1d2d4d;
}
.stats-label {
  font-size: 14px;
  color: #7b8aa2;
}
</style>
