<script setup lang="ts">
import { onMounted } from 'vue';

const adminUrl = import.meta.env.VITE_ADMIN_APP_URL || 'http://127.0.0.1:5174/';
const openAdmin = () => window.location.replace(adminUrl);

onMounted(() => {
  openAdmin();
});
</script>

<template>
  <main class="redirect-page">
    <section>
      <h1>正在进入独立运营后台</h1>
      <p>员工账号与求职者账号使用独立登录体系。</p>
      <el-button type="primary" @click="openAdmin">立即前往</el-button>
    </section>
  </main>
</template>

<style scoped>
.redirect-page { min-height: 60vh; display: grid; place-items: center; padding: 32px; }
.redirect-page section { max-width: 480px; text-align: center; }
.redirect-page h1 { margin: 0 0 12px; font-size: 26px; }
.redirect-page p { margin: 0 0 20px; color: #667085; }
</style>
