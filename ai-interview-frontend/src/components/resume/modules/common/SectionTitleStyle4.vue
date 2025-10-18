<!-- src/components/resume/modules/common/SectionTitleStyle4.vue -->
<template>
  <div class="title-wrapper-sidebar">
    <h3 class="title-text">{{ text }}</h3>
  </div>
</template>

<script setup lang="ts">
defineProps({
  text: { type: String, default: '模块标题' },
});
</script>

<style scoped>
.title-wrapper-sidebar {
  display: flex;
  flex-direction: column;
  align-items: center; /* 居中对齐 */
  margin-bottom: 20px;
}
.title-text {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #fff; /* 白色文字 */
  padding-bottom: 5px;
  border-bottom: 2px solid rgba(255, 255, 255, 0.5); /* 半透明下划线 */
}
</style>