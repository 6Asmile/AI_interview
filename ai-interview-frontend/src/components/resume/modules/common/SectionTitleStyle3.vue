<!-- src/components/resume/modules/common/SectionTitleStyle3.vue -->
<template>
  <div class="title-wrapper">
    <div class="title-box">
      <h3 class="title-text">{{ text }}</h3>
    </div>
    <div class="lozenge-1"></div>
    <div class="lozenge-2"></div>
    <div class="left-line"></div>
  </div>
</template>

<script setup lang="ts">
defineProps({
  text: { type: String, default: '模块标题' },
});
</script>

<style scoped>
/* 这些样式精确复刻了您提供的模板中的标题样式 */
.title-wrapper {
  width: 100%;
  height: 30px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #808080;
  position: relative; /* 为绝对定位的装饰元素提供基准 */
  margin-bottom: 20px; /* 增加标题和内容之间的距离 */
}

.title-box {
  background-color: #808080; /* 灰色背景 */
  padding: 0 15px;
  height: 100%;
  display: flex;
  align-items: center;
}

.title-text {
  font-size: 18px;
  font-weight: 500;
  color: #fff; /* 白色文字 */
  letter-spacing: 2px;
}

/* 菱形和线条装饰 */
.lozenge-1, .lozenge-2, .left-line {
  background-color: #808080;
  position: absolute;
}
.lozenge-1 {
  width: 14.5px;
  height: 14.5px;
  transform: rotate(45deg);
  left: 35px;
  top: 7.75px;
}
.lozenge-2 {
  width: 7px;
  height: 7px;
  transform: rotate(45deg);
  left: 38.75px;
  top: 11.75px;
  background-color: #fff;
}
.left-line {
  height: calc(100% - 14.5px);
  top: 14.5px;
  left: 42px; /* 调整以对齐菱形中心 */
  width: 1px;
}
</style>