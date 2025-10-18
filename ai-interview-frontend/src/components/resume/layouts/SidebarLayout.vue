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
.sidebar-layout {
  display: flex;
  width: 100%;
  height: 100%;
}
.sidebar {
  width: 270px; /* 左侧栏固定宽度 */
  background-color: rgb(37, 70, 101); /* 深蓝色背景 */
  color: #fff; /* 白色文字 */
  padding: 30px 20px;
  flex-shrink: 0;
}
.main-content {
  flex-grow: 1;
  background-color: #fff;
  padding: 25px 20px;
}
</style>