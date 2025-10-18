<!-- src/components/resume/editor/ResumeCanvas.vue -->
<template>
  <div class="resume-paper" :style="pageStyles">
    <!-- 场景一：单栏布局 -->
    <template v-if="currentLayout === 'single-column'">
      <div v-if="allVisibleModules.length > 0" class="canvas-area">
        <div 
          v-for="element in allVisibleModules" 
          :key="element.id"
          :id="`canvas-module-${element.id}`"  
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === editorStore.selectedComponentId }]"
          @click.stop="isEditor && handleClickCanvasModule(element.id)"
        >
          <component 
            :is="componentMap[element.componentName]" 
            v-bind="element.props" 
            :style="element.styles" 
          />
        </div>
      </div>
      <div v-else class="empty-tip"><el-empty description="请从左侧添加和配置模块" /></div>
    </template>

    <!-- 场景二：左右分栏布局 -->
    <SidebarLayout v-if="currentLayout === 'sidebar'">
      <template #sidebar>
        <div 
          v-for="element in sidebarModules" 
          :key="element.id"
          :id="`canvas-module-${element.id}`"
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === editorStore.selectedComponentId }]"
          @click.stop="isEditor && handleClickCanvasModule(element.id)"
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
          :id="`canvas-module-${element.id}`"
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === editorStore.selectedComponentId }]"
          @click.stop="isEditor && handleClickCanvasModule(element.id)"
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
import { computed, markRaw, nextTick, watch } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { templates } from '@/resume-templates';
import { ElEmpty } from 'element-plus';
import SidebarLayout from '../layouts/SidebarLayout.vue';
import BaseInfoModule from '../modules/BaseInfoModule.vue';
import SummaryModule from '../modules/SummaryModule.vue';
import EducationModule from '../modules/EducationModule.vue';
import WorkExpModule from '../modules/WorkExpModule.vue';
import ProjectModule from '../modules/ProjectModule.vue';
import SkillsModule from '../modules/SkillsModule.vue';
import GenericListModule from '../modules/GenericListModule.vue';
import CustomModule from '../modules/CustomModule.vue';

// 【核心修复】移除未使用的 props
defineProps({
  isEditor: { type: Boolean, default: true }
});

const editorStore = useResumeEditorStore();

const currentTemplate = computed(() => templates.find(t => t.id === editorStore.selectedTemplateId) || templates[0]);
const currentLayout = computed(() => currentTemplate.value.layout);
const pageStyles = computed(() => currentTemplate.value.pageStyles || {});
const allVisibleModules = computed(() => [...editorStore.resumeJson.sidebar, ...editorStore.resumeJson.main].filter(m => m.props.show !== false));
const sidebarModules = computed(() => editorStore.resumeJson.sidebar.filter(m => m.props.show !== false));
const mainModules = computed(() => editorStore.resumeJson.main.filter(m => m.props.show !== false));

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

watch(() => editorStore.selectedComponentId, (newId) => {
  if (newId) {
    const element = document.getElementById(`canvas-item-${newId}`);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
});

// --- 【核心新增】点击画布模块的处理函数 ---
const handleClickCanvasModule = (moduleId: string) => {
    // 1. 更新Store中的选中状态
    editorStore.selectComponent(moduleId);

    // 2. 触发滚动到左侧配置面板的逻辑
    scrollToConfigModule(moduleId);
};

// --- 【核心新增】滚动到左侧配置面板的函数 ---
const scrollToConfigModule = (moduleId: string) => {
    nextTick(() => {
        // 构造左侧模块的 ID (注意，我们需要滚动的是 el-collapse-item 的 header)
        const targetId = `config-module-header-${moduleId}`;
        const targetElement = document.getElementById(targetId);

        if (targetElement) {
            targetElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
            });
            
            // 可以在这里找到对应的 el-collapse-item 并手动展开它
            // 但因为 ConfigPanel 内部已经有展开逻辑，所以这里可以简化
        }
    });
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
  border-bottom: none; 
  /* 【核心修复】为包裹层添加白色背景 */
  background-color: #fff;
}
.canvas-area .canvas-component-item:not(:last-child) {
    border-bottom: 1px solid #f0f0f0;
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