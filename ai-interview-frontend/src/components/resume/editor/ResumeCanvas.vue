<!-- src/components/resume/editor/ResumeCanvas.vue -->
<template>
  <div class="resume-paper" :style="pageStyles">
    <!-- 场景一：单栏布局 -->
    <template v-if="currentLayout === 'single-column'">
      <div v-if="visibleModules.length > 0" class="canvas-area">
        <div 
          v-for="element in visibleModules" 
          :key="element.id" 
          :class="['canvas-component-item', { 'is-selected': element.id === editorStore.selectedComponentId }]"
          @click.stop="editorStore.selectComponent(element.id)"
        >
          <component 
            :is="componentMap[element.componentName]" 
            v-bind="element.props" 
            :style="element.styles" 
          />
        </div>
      </div>
      <div v-else class="empty-tip">
        <el-empty description="请从左侧添加和配置模块" />
      </div>
    </template>

    <!-- 场景二：左右分栏布局 -->
    <SidebarLayout v-if="currentLayout === 'sidebar'">
      <template #sidebar>
        <div 
          v-for="element in sidebarModules" 
          :key="element.id" 
          :class="['canvas-component-item', { 'is-selected': element.id === editorStore.selectedComponentId }]"
          @click.stop="editorStore.selectComponent(element.id)"
        >
          <component 
            :is="componentMap[element.componentName]" 
            v-bind="element.props" 
            :style="element.styles" 
          />
        </div>
      </template>
      <template #main>
        <div 
          v-for="element in mainModules" 
          :key="element.id" 
          :class="['canvas-component-item', { 'is-selected': element.id === editorStore.selectedComponentId }]"
          @click.stop="editorStore.selectComponent(element.id)"
        >
          <component 
            :is="componentMap[element.componentName]" 
            v-bind="element.props" 
            :style="element.styles" 
          />
        </div>
      </template>
    </SidebarLayout>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { templates } from '@/resume-templates';
import { ElEmpty } from 'element-plus';

// 导入所有需要的组件
import SidebarLayout from '../layouts/SidebarLayout.vue';
import BaseInfoModule from '../modules/BaseInfoModule.vue';
import SummaryModule from '../modules/SummaryModule.vue';
import EducationModule from '../modules/EducationModule.vue';
import WorkExpModule from '../modules/WorkExpModule.vue';
import ProjectModule from '../modules/ProjectModule.vue';
import SkillsModule from '../modules/SkillsModule.vue';
import GenericListModule from '../modules/GenericListModule.vue';
import CustomModule from '../modules/CustomModule.vue';

const editorStore = useResumeEditorStore();

// 计算当前选择的模板对象
const currentTemplate = computed(() => {
  return templates.find(t => t.id === editorStore.selectedTemplateId) || templates[0];
});

// 计算当前布局模式 ('single-column' 或 'sidebar')
const currentLayout = computed(() => currentTemplate.value.layout);

// 计算全局页面样式
const pageStyles = computed(() => currentTemplate.value.pageStyles || {});

// 计算所有可见的模块
const visibleModules = computed(() => 
  editorStore.resumeJson.filter(m => m.props.show !== false)
);

// 计算应该放在侧边栏的模块
const sidebarModules = computed(() => 
  visibleModules.value.filter(m => m.props.layoutZone === 'sidebar')
);

// 计算应该放在主内容区的模块
const mainModules = computed(() => 
  visibleModules.value.filter(m => m.props.layoutZone !== 'sidebar')
);

// 注册所有模块组件
const componentMap: Record<string, any> = {
  BaseInfoModule: markRaw(BaseInfoModule),
  SummaryModule: markRaw(SummaryModule),
  EducationModule: markRaw(EducationModule),
  WorkExpModule: markRaw(WorkExpModule),
  ProjectModule: markRaw(ProjectModule),
  SkillsModule: markRaw(SkillsModule),
  GenericListModule: markRaw(GenericListModule),
  CustomModule: markRaw(CustomModule),
};
</script>

<style scoped>
.resume-paper {
  width: 210mm;
  min-height: 297mm;
  background-color: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  margin: 0 auto;
  transition: all 0.3s;
}
.canvas-area {
  min-height: 297mm;
  width: 100%;
}
.canvas-component-item {
  border: 1px dashed transparent;
  cursor: pointer;
}
.canvas-component-item:hover {
  border-color: #c6e2ff;
}
.canvas-component-item.is-selected {
  border: 1px solid #409eff;
  position: relative;
}
.empty-tip {
  padding-top: 100px;
}
</style>