<!-- src/components/resume/modules/GenericListModule.vue -->
<template>
  <div class="generic-list-module">
    <component :is="titleComponent" :text="title" />
    <div v-for="item in items" :key="item.id" class="item">
      <div class="item-header">
        <span class="main-info">{{ item.title }}</span>
        <span class="sub-info">{{ item.subtitle }}</span>
      </div>
      <!-- 【核心修改】 -->
      <div v-if="item.description" class="description" v-html="item.description"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import SectionTitle from './common/SectionTitle.vue';
import SectionTitleStyle2 from './common/SectionTitleStyle2.vue';
import SectionTitleStyle3 from './common/SectionTitleStyle3.vue';
import SectionTitleStyle4 from './common/SectionTitleStyle4.vue';

interface ListItem {
  id: string;
  title: string;
  subtitle: string;
  description: string;
}

const props = defineProps({
  title: { type: String, default: '模块标题' },
  titleStyle: { type: String, default: 'style1' },
  items: { type: Array as () => ListItem[], default: () => [] }
});

const titleComponent = computed(() => {
  if (props.titleStyle === 'style2') return markRaw(SectionTitleStyle2);
  if (props.titleStyle === 'style3') return markRaw(SectionTitleStyle3);
  if (props.titleStyle === 'style4') return markRaw(SectionTitleStyle4);
  return markRaw(SectionTitle);
});
</script>

<style scoped>
.item { margin-bottom: 12px; }
.item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
.main-info { font-weight: 600; }
.sub-info { color: #555; font-style: italic; }

/* 【核心修改】 */
.description {
  font-size: 14px;
  color: #555;
  line-height: 1.8;
  font-family: inherit;
  margin-left: 8px; /* 保持一点缩进 */
}
.description :deep(p) { margin: 0; }
.description :deep(ul), .description :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
</style>