<!-- src/components/resume/modules/common/SectionTitleStyle4.vue -->
<template>
  <div class="title-wrapper">
    <div class="title-icon-box">
      <!-- 暂时用 Element Plus 图标代替，未来可以换成 SVG -->
      <el-icon><component :is="iconComponent" /></el-icon>
    </div>
    <h3 class="title-text">{{ text }}</h3>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
// 导入一些可能用到的图标
import { CollectionTag, Medal, Star } from '@element-plus/icons-vue';

const props = defineProps({
  text: { type: String, default: '模块标题' },
  // 接收一个图标名
  icon: { type: String, default: 'CollectionTag' }
});

// 简单的图标映射
const iconMap: Record<string, any> = {
  CollectionTag,
  Medal,
  Star,
};

const iconComponent = computed(() => iconMap[props.icon] || CollectionTag);
</script>

<style scoped>
.title-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
}
.title-icon-box {
  font-size: 30px;
  margin-bottom: 8px;
}
.title-text {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 2px;
}
</style>