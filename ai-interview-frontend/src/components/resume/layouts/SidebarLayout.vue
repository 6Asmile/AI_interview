<!-- src/components/resume/layouts/SidebarLayout.vue -->
<template>
  <div class="sidebar-layout">
    <div class="sidebar">
      <!-- 渲染左侧栏模块 -->
      <slot name="sidebar"></slot>
    </div>
    <div class="main-content">
      <!-- 渲染主内容区模块 -->
      <slot name="main"></slot>
    </div>
  </div>
</template>

<style scoped>
.sidebar-layout { display: flex; width: 100%; min-height: 297mm; /* 确保撑满高度 */ }
.sidebar {
  width: 35%; /* 使用百分比，更灵活 */
  max-width: 280px;
  /* 【核心修复】使用更专业、更柔和的蓝色 */
  background-color: #aacff5; 
  color: #fff;
  padding: 40px 25px;
  flex-shrink: 0;
}
.main-content {
  flex-grow: 1;
  background-color: #fff;
  padding-top: 40px; /* 与侧边栏顶部对齐 */
}
</style>