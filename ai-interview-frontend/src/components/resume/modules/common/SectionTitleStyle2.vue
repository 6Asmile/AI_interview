<!-- src/components/resume/modules/common/SectionTitleStyle2.vue -->
<template>
  <div class="title-wrapper">
    <h3 class="title-text">{{ text }}</h3>
  </div>
</template>

<script setup lang="ts">
defineProps({
  text: { type: String, default: '模块标题' },
});
</script>

<style scoped>
/* 这些样式复刻了您提供的模板中的标题样式 */
.title-wrapper {
  width: 100%;
  height: 40px;
  color: rgb(37, 70, 101);
  display: flex;
  align-items: center;
  margin-bottom: 15px;
  border-bottom: 1px solid rgb(37, 70, 101);
}
.title-text {
  height: 100%;
  font-size: 20px;
  font-weight: 600;
  color: rgb(37, 70, 101);
  display: flex;
  align-items: center;
  border-bottom: 3px solid rgb(37, 70, 101);
  letter-spacing: 2px;
}
</style>