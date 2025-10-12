<!-- src/components/resume/editor/ResumeCanvas.vue -->
<template>
  <div class="resume-canvas-container" @click="deselectComponent">
    <div class="resume-canvas">
      <draggable
        v-model="resumeJson"
        item-key="id"
        group="resume-components"
        class="canvas-area"
        ghost-class="ghost"
        handle=".drag-handle"
        @add="onAddComponent"
      >
        <template #item="{ element }">
          <div
            :class="['canvas-component-item', { 'is-selected': element.id === editorStore.selectedComponentId }]"
            @click.stop="selectComponent(element.id)"
          >
            <!-- 动态渲染所有模块 -->
            <component
              :is="componentMap[element.componentName]"
              v-bind="element.props"
              :style="element.styles"
            />
            <div class="component-actions">
              <el-button type="primary" :icon="Rank" circle size="small" class="drag-handle" />
              <el-button type="danger" :icon="Delete" circle size="small" @click.stop="deleteComponent(element.id)" />
            </div>
          </div>
        </template>
      </draggable>
      <div v-if="!resumeJson.length" class="empty-tip">
        <el-empty description="从左侧拖拽组件到此处开始" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue';
import draggable from 'vuedraggable';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { Delete, Rank } from '@element-plus/icons-vue';

// 导入所有简历模块组件
import BaseInfoModule from '../modules/BaseInfoModule.vue';
import SummaryModule from '../modules/SummaryModule.vue';
import EducationModule from '../modules/EducationModule.vue';
import WorkExpModule from '../modules/WorkExpModule.vue';
import ProjectModule from '../modules/ProjectModule.vue';
import SkillsModule from '../modules/SkillsModule.vue';

const editorStore = useResumeEditorStore();

const resumeJson = computed({
  get: () => editorStore.resumeJson,
  set: (value) => { editorStore.resumeJson = value; },
});

// 【核心】注册所有组件到 map 中
const componentMap: Record<string, any> = {
  BaseInfoModule: markRaw(BaseInfoModule),
  SummaryModule: markRaw(SummaryModule),
  EducationModule: markRaw(EducationModule),
  WorkExpModule: markRaw(WorkExpModule),
  ProjectModule: markRaw(ProjectModule),
  SkillsModule: markRaw(SkillsModule),
};

const selectComponent = (id: string) => editorStore.selectComponent(id);
const deleteComponent = (id: string) => editorStore.deleteComponent(id);
const deselectComponent = () => editorStore.selectComponent(null);

const onAddComponent = (event: any) => {
  const newComponent = resumeJson.value[event.newIndex];
  if (newComponent) {
    selectComponent(newComponent.id);
  }
};
</script>

<style>
.ghost { opacity: 0.5; background: #c8ebfb; }
</style>
<style scoped>
/* 样式与之前保持一致，无需修改 */
.resume-canvas-container { width: 100%; height: 100%; }
.resume-canvas { width: 210mm; min-height: 297mm; background-color: #fff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); margin: 0 auto; }
.canvas-area { min-height: 297mm; width: 100%; }
.canvas-component-item { position: relative; border: 1px dashed transparent; transition: border-color 0.2s; cursor: pointer; }
.canvas-component-item:hover { border-color: #c6e2ff; }
.canvas-component-item.is-selected { border: 1px solid #409eff; }
.component-actions { display: none; position: absolute; top: 50%; right: -35px; transform: translateY(-50%); flex-direction: column; gap: 8px; }
.canvas-component-item.is-selected .component-actions { display: flex; }
.drag-handle { cursor: grab; }
.empty-tip { padding-top: 100px; }
</style>