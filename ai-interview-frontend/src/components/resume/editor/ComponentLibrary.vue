<!-- src/components/resume/editor/ComponentLibrary.vue -->
<template>
  <div class="component-library">
    <h3 class="panel-title">我的简历模块</h3>
    <p class="panel-desc">点击下方模块进行编辑，或拖拽调整顺序</p>
    
    <draggable
      v-model="editorStore.resumeJson"
      item-key="id"
      handle=".drag-indicator"
      class="added-modules-list"
    >
      <template #item="{ element }">
        <div 
          class="added-module-item"
          :class="{ 'is-active': false }" 
          @click="scrollToModule(element.id)"
        >
          <el-icon class="drag-indicator"><Rank /></el-icon>
          <span>{{ element.title }}</span>
          <el-icon class="delete-icon" @click.stop="editorStore.deleteComponent(element.id)"><Close /></el-icon>
        </div>
      </template>
    </draggable>

    <div class="add-module-btn" @click="dialogVisible = true">
      <el-icon><Plus /></el-icon>
      <span>添加模块</span>
    </div>

    <el-dialog v-model="dialogVisible" title="添加新模块" width="60%">
      <div class="module-pool">
        <div 
          v-for="template in availableTemplates" 
          :key="template.componentName"
          class="module-pool-item"
          @click="addModule(template)"
        >
          <el-icon><component :is="template.icon" /></el-icon>
          <span>{{ template.title }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import draggable from 'vuedraggable';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
// 【核心修改】从新文件中导入模块定义
import { allTemplates, type ModuleTemplate } from '@/resume-templates/template-definitions';
import { Rank, Close, Plus } from '@element-plus/icons-vue';

const editorStore = useResumeEditorStore();
const dialogVisible = ref(false);

const availableTemplates = computed(() => {
  const addedComponentNames = new Set(editorStore.resumeJson.map(c => c.componentName));
  return allTemplates.filter(t => !addedComponentNames.has(t.componentName));
});

const addModule = (template: ModuleTemplate) => {
  editorStore.addComponent(template.componentName);
  dialogVisible.value = false;
};

// 增加一个滚动到对应模块的功能，提升体验
const scrollToModule = (moduleId: string) => {
  // 这里的实现需要 ConfigPanel 支持，暂时留空
  console.log('Scroll to:', moduleId);
};
</script>

<style scoped>
/* 样式保持不变 */
.panel-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.panel-desc { font-size: 12px; color: #999; margin-bottom: 16px; }
.added-modules-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.added-module-item { display: flex; align-items: center; padding: 8px 12px; border: 1px solid #e8e8e8; border-radius: 4px; cursor: pointer; background-color: #fff; }
.added-module-item.is-active { border-color: #409eff; background-color: #ecf5ff; }
.drag-indicator { cursor: grab; color: #999; margin-right: 8px; }
.delete-icon { margin-left: auto; color: #999; cursor: pointer; }
.delete-icon:hover { color: #f56c6c; }
.add-module-btn { display: flex; align-items: center; justify-content: center; width: 100%; padding: 10px; border: 1px dashed #dcdfe6; border-radius: 4px; color: #409eff; cursor: pointer; background-color: #f9f9f9; }
.add-module-btn:hover { border-color: #409eff; background-color: #ecf5ff; }
.module-pool { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 16px; }
.module-pool-item { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 16px 8px; border: 1px solid #e8e8e8; border-radius: 4px; cursor: pointer; }
.module-pool-item:hover { border-color: #409eff; color: #409eff; }
.module-pool-item .el-icon { font-size: 24px; margin-bottom: 8px; }
</style>