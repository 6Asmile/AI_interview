<template>
  <div id="app-container">
    <div class="particles">
      <div class="particle"></div>
      <div class="particle"></div>
      <div class="particle"></div>
      <div class="particle"></div>
    </div>
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

/* 根容器，应用渐变背景 */
#app-container {
  position: relative;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); /* 一个柔和的蓝灰色渐变 */
  overflow-y: auto; /* 只允许内容区域垂直滚动 */
  scroll-behavior: smooth; /* 全局平滑滚动 */
}

/* 粒子效果容器 */
.particles {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none; /* 让粒子不影响鼠标点击 */
}

/* 单个粒子样式和动画 */
.particle {
  position: absolute;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 50%;
  animation: float 25s ease-in-out infinite;
}

/* 为每个粒子设置不同的大小、位置和动画延迟 */
.particle:nth-child(1) {
  width: 10px;
  height: 10px;
  left: 15%;
  animation-duration: 20s;
}
.particle:nth-child(2) {
  width: 20px;
  height: 20px;
  left: 40%;
  animation-duration: 25s;
  animation-delay: 2s;
}
.particle:nth-child(3) {
  width: 15px;
  height: 15px;
  left: 70%;
  animation-duration: 30s;
  animation-delay: 5s;
}
.particle:nth-child(4) {
  width: 8px;
  height: 8px;
  left: 90%;
  animation-duration: 15s;
  animation-delay: 8s;
}

/* 粒子漂浮动画 */
@keyframes float {
  0% {
    transform: translateY(0) rotate(0deg);
    opacity: 1;
    border-radius: 50%;
  }
  50% {
    transform: translateY(-800px) rotate(360deg);
    opacity: 0.5;
  }
  100% {
    transform: translateY(0) rotate(720deg);
    opacity: 1;
    border-radius: 50%;
  }
}
</style>