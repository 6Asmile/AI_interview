<!-- src/components/resume/modules/common/SectionTitle.vue -->
<template>
  <div class="module-title-wrapper" :style="wrapperStyle">
    <h3 class="module-title-text" :style="textStyle">{{ text }}</h3>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps({
  text: { type: String, default: '模块标题' },
});

// 这些样式复刻了您提供的模板中的标题样式
const wrapperStyle = computed(() => ({
  width: '100%',
  height: '32px',
  backgroundColor: '#f3f3f3',
  display: 'flex',
  justifyContent: 'flex-start',
  alignItems: 'center',
  marginBottom: '15px',
}));

const textStyle = computed(() => ({
  height: '100%',
  backgroundColor: 'rgb(37, 70, 101)',
  fontSize: '20px',
  fontWeight: 600,
  color: '#fff',
  display: 'flex',
  alignItems: 'center',
  paddingLeft: '50px',
  paddingRight: '20px',
  letterSpacing: '2px',
}));
</script>