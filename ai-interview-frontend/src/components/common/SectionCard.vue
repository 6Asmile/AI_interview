<template>
  <div class="section-card">
    <h3 class="section-title">{{ title }}</h3>
    <div class="section-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
}>();
</script>

<style scoped>
.section-card {
  margin-bottom: 20px;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 15px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}
</style>