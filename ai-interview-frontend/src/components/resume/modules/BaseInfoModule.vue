<!-- src/components/resume/modules/BaseInfoModule.vue -->
<template>
  <div class="base-info-module">
    <div class="info-content">
      <h1 class="name">{{ name }}</h1>
      <div class="info-items">
        <span v-for="item in items" :key="item.id" class="info-item">
          <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
          {{ item.label }}: {{ item.value }}
        </span>
      </div>
    </div>
    <div v-if="photo" class="photo-container">
      <img :src="fullPhotoUrl" alt="avatar" />
    </div>
  </div>
</template>

<script setup lang="ts">
// --- 【核心修复】从 'vue' 中导入 computed ---
import { computed } from 'vue';

interface InfoItem {
  id: string;
  icon: string;
  label: string;
  value: string;
}

const props = defineProps({
  name: { type: String, default: '' },
  photo: { type: String, default: '' },
  items: { type: Array as () => InfoItem[], default: () => [] },
});

const fullPhotoUrl = computed(() => {
  if (!props.photo) return '';
  if (props.photo.startsWith('blob:') || props.photo.startsWith('http')) {
    return props.photo;
  }
  const baseUrl = import.meta.env.VITE_API_BASE_URL.split('/api/v1')[0];
  return `${baseUrl}${props.photo}`;
});
</script>

<style scoped>
.base-info-module {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.name {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 12px;
}
.info-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px; /* 调整间距 */
  color: #555;
  font-size: 14px;
}
.info-item {
  display: inline-flex; /* 让 icon 和 text 对齐 */
  align-items: center;
  gap: 4px; /* icon 和 text 的间距 */
}
.photo-container {
  width: 100px;
  height: 120px;
  border: 1px solid #eee;
  flex-shrink: 0;
  margin-left: 20px; /* 增加与左侧内容的间距 */
}
.photo-container img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>