<!-- src/components/resume/modules/BaseInfoModule.vue -->
<template>
  <div class="base-info-module" :class="{ 'sidebar-mode': layoutZone === 'sidebar' }">
    <!-- 头像 -->
    <div v-if="photo" class="photo-container">
      <img :src="fullPhotoUrl" alt="avatar" />
    </div>
    
    <!-- 信息内容 -->
    <div class="info-content">
      <h1 class="name">{{ name }}</h1>
      <div class="info-items">
        <div v-for="item in items" :key="item.id" class="info-item">
          <!-- 可以根据 item.icon 动态渲染图标 -->
          <span class="label">{{ item.label }}:</span>
          <span class="value">{{ item.value }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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
  layoutZone: { type: String, default: 'main' }, // 接收布局区域信息
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
/* 默认（主内容区）样式 */
.base-info-module {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.photo-container {
  width: 100px;
  height: 120px;
  border: 1px solid #eee;
  flex-shrink: 0;
  margin-left: 20px;
}
.name { font-size: 28px; font-weight: 600; margin-bottom: 12px; }
.info-items { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 14px; }
.info-item .label { color: #888; }
.info-item .value { color: #333; }

/* 侧边栏模式下的特定样式 */
.base-info-module.sidebar-mode {
  flex-direction: column; /* 垂直布局 */
  align-items: center; /* 居中对齐 */
  text-align: center;
  color: #fff; /* 文字颜色变为白色 */
}
.sidebar-mode .photo-container {
  width: 120px;
  height: 120px;
  border-radius: 50%; /* 圆形头像 */
  overflow: hidden;
  border: 3px solid rgba(255, 255, 255, 0.5);
  margin-left: 0;
  margin-bottom: 20px;
}
.sidebar-mode .name { color: #fff; }
.sidebar-mode .info-items {
  flex-direction: column; /* 垂直排列 */
  align-items: center;
  gap: 10px;
}
.sidebar-mode .info-item .label,
.sidebar-mode .info-item .value {
  color: rgba(255, 255, 255, 0.85); /* 半透明白色 */
}

/* 通用样式 */
.photo-container img { width: 100%; height: 100%; object-fit: cover; }
</style>