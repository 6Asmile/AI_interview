<!-- src/components/resume/modules/BaseInfoModule.vue -->
<template>
  <div class="base-info-module">
    <div class="info-content">
      <h1 class="name">{{ name }}</h1>
      <div class="info-items">
        <span v-for="item in items" :key="item.id" class="info-item">
          {{ item.label }}: {{ item.value }}
        </span>
      </div>
    </div>
    <div v-if="photo" class="photo-container">
      <img :src="photo" alt="avatar" />
    </div>
  </div>
</template>

<script setup lang="ts">
interface InfoItem {
  id: string;
  icon: string;
  label: string;
  value: string;
}

defineProps({
  name: { type: String, default: '' },
  photo: { type: String, default: '' },
  items: { type: Array as () => InfoItem[], default: () => [] },
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
  gap: 16px;
  color: #555;
  font-size: 14px;
}
.photo-container {
  width: 100px;
  height: 120px;
  border: 1px solid #eee;
  flex-shrink: 0;
}
.photo-container img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>