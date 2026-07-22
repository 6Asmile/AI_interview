<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { Monitor } from '@element-plus/icons-vue';

defineProps<{ feature?: string }>();
const isNarrow = ref(false);
let query: MediaQueryList | null = null;
const update = () => { isNarrow.value = Boolean(query?.matches); };
onMounted(() => {
  query = window.matchMedia('(max-width: 767px)');
  update();
  query.addEventListener('change', update);
});
onBeforeUnmount(() => query?.removeEventListener('change', update));
</script>

<template>
  <slot v-if="!isNarrow" />
  <section v-else class="desktop-required" aria-labelledby="desktop-required-title">
    <el-icon :size="36"><Monitor /></el-icon>
    <h1 id="desktop-required-title">请使用桌面端继续</h1>
    <p>{{ feature || '该功能' }}包含复杂编辑与实时交互，为保证内容完整和操作安全，请在宽度不少于 768px 的桌面浏览器中使用。</p>
    <router-link to="/dashboard">返回求职概览</router-link>
  </section>
</template>

<style scoped>
.desktop-required { min-height: calc(100vh - 60px); display: grid; place-content: center; justify-items: center; gap: 12px; padding: 28px; color: #344054; background: #f7f9fc; text-align: center; }
.desktop-required h1 { margin: 4px 0 0; font-size: 24px; letter-spacing: 0; }
.desktop-required p { max-width: 520px; margin: 0; color: #667085; line-height: 1.7; }
.desktop-required a { margin-top: 8px; color: #2563eb; text-decoration: none; }
</style>
