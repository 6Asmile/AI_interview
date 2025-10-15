<!-- src/components/resume/editor/ResumeCanvas.vue -->
<template>
  <div class="resume-paper" :style="pageStyles">
    <div v-if="editorStore.resumeJson.length > 0" class="canvas-area">
      <div v-for="element in visibleModules" :key="element.id">
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
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { templates } from '@/resume-templates';
import { ElEmpty } from 'element-plus';
// 导入所有模块组件
import BaseInfoModule from '../modules/BaseInfoModule.vue';
import SummaryModule from '../modules/SummaryModule.vue';
import EducationModule from '../modules/EducationModule.vue';
import WorkExpModule from '../modules/WorkExpModule.vue';
import ProjectModule from '../modules/ProjectModule.vue';
import SkillsModule from '../modules/SkillsModule.vue';
import GenericListModule from '../modules/GenericListModule.vue';
import CustomModule from '../modules/CustomModule.vue';

const editorStore = useResumeEditorStore();

const pageStyles = computed(() => {
  const currentTemplate = templates.find(t => t.id === editorStore.selectedTemplateId);
  return currentTemplate?.pageStyles || {};
});

// 只渲染 show=true 的模块
const visibleModules = computed(() => 
  editorStore.resumeJson.filter(m => m.props.show !== false)
);

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
.canvas-area { min-height: 297mm; width: 100%; }
.empty-tip { padding-top: 100px; }
</style>