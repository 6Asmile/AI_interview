<!-- src/components/resume/modules/CustomModule.vue -->
<template>
  <div class="custom-module">
    <component :is="titleComponent" :text="title" />
    <pre class="section-content">{{ content }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';

const props = defineProps({
  title: { type: String, default: '自定义标题' },
  titleStyle: { type: String, default: 'style1' },
  content: { type: String, default: '' }
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
.section-content {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  white-space: pre-wrap;
  font-family: inherit;
}
</style>