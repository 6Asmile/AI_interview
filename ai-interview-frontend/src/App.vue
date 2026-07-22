<template>
  <div id="app-container">
    <router-view />
  </div>
</template>

<script setup lang="ts">
// No script logic needed here
</script>

<style>
/* 全局样式 */
html, body, #app, #app-container {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
  overflow: hidden; /* 防止背景元素导致滚动条 */
}

#app-container {
  position: relative;
  background: #f5f7fa;
  overflow-y: auto; /* 只允许内容区域垂直滚动 */
  scroll-behavior: smooth; /* 全局平滑滚动 */
}

</style>
