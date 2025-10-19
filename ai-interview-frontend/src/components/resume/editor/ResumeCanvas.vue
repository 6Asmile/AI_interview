<!-- src/components/resume/editor/ResumeCanvas.vue -->
<template>
  <div class="resume-paper" :style="pageStyles">
    <!-- 场景一：单栏布局 -->
    <template v-if="currentLayout === 'single-column'">
      <div v-if="allVisibleModules.length > 0" class="canvas-area">
        <div 
          v-for="element in allVisibleModules" 
          :key="element.id" 
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === selectedComponentId }]"
          @click.stop="isEditor && selectComponent(element.id)"
          :style="element.styles"
        >
          <component 
            :is="componentMap[element.componentName]" 
            v-bind="element.props" 
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
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === selectedComponentId }]"
          @click.stop="isEditor && selectComponent(element.id)"
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
          :class="['canvas-component-item', { 'is-selected': isEditor && element.id === selectedComponentId }]"
          @click.stop="isEditor && selectComponent(element.id)"
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
import { useResumeEditorStore, type ResumeLayout } from '@/store/modules/resumeEditor';
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

const props = defineProps({
  isEditor: { type: Boolean, default: true },
  // 用于预览页的 props
  resumeJsonProp: { type: Object as () => ResumeLayout, default: null },
  templateIdProp: { type: String, default: null }
});

const editorStore = useResumeEditorStore();

// --- 核心逻辑：数据源二选一 ---
const resumeJson = computed(() => props.resumeJsonProp || editorStore.resumeJson);
const selectedTemplateId = computed(() => props.templateIdProp || editorStore.selectedTemplateId);
const selectedComponentId = computed(() => props.isEditor ? editorStore.selectedComponentId : null);

const selectComponent = (id: string) => {
    if (props.isEditor) {
        editorStore.selectComponent(id);
    }
};

// --- 计算属性保持不变 ---
const currentTemplate = computed(() => templates.find(t => t.id === selectedTemplateId.value) || templates[0]);
const currentLayout = computed(() => currentTemplate.value.layout);
const pageStyles = computed(() => currentTemplate.value.pageStyles || {});

const allModules = computed(() => [...resumeJson.value.sidebar, ...resumeJson.value.main]);
const allVisibleModules = computed(() => allModules.value.filter(m => m.props.show !== false));
const sidebarModules = computed(() => resumeJson.value.sidebar.filter(m => m.props.show !== false));
const mainModules = computed(() => resumeJson.value.main.filter(m => m.props.show !== false));

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
.resume-paper { width: 210mm; min-height: 297mm; background-color: #fff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); margin: 0 auto; transition: all 0.3s; }
.canvas-area { min-height: 297mm; width: 100%; }
.canvas-component-item { border: 1px dashed transparent; cursor: pointer; }
.canvas-area .canvas-component-item:not(:last-child) { border-bottom: 1px solid #f0f0f0; }
.canvas-component-item:hover { border-color: #c6e2ff; }
.canvas-component-item.is-selected { border: 1px solid #409eff; position: relative; }
.empty-tip { padding-top: 100px; }
</style>