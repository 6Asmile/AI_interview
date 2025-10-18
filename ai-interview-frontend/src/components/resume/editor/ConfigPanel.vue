<!-- src/components/resume/editor/ConfigPanel.vue -->
<template>
  <div class="config-panel">
    <!-- 侧边栏模块列表 -->
    <div class="zone-wrapper">
      <div class="zone-header">
        <span class="zone-title">侧边栏模块</span>
        <el-button link type="primary" :icon="Plus" @click="openAddDialog('sidebar')" />
      </div>
      <draggable
        v-model="sidebarJson"
        item-key="id"
        handle=".drag-handle"
        class="module-list"
        ghost-class="ghost"
        group="resumeModules"
      >
        <template #item="{ element: module }">
          <ModuleFormItem :module="module" />
        </template>
      </draggable>
    </div>

    <!-- 主区域模块列表 -->
    <div class="zone-wrapper">
      <div class="zone-header">
        <span class="zone-title">主内容区模块</span>
        <el-button link type="primary" :icon="Plus" @click="openAddDialog('main')" />
      </div>
      <draggable
        v-model="mainJson"
        item-key="id"
        handle=".drag-handle"
        class="module-list"
        ghost-class="ghost"
        group="resumeModules"
      >
        <template #item="{ element: module }">
          <ModuleFormItem :module="module" />
        </template>
      </draggable>
    </div>
    
    <!-- 统一的“添加模块”弹窗 -->
    <el-dialog v-model="dialogVisible" title="添加新模块" width="60%">
        <div class="module-pool">
            <div 
            v-for="template in availableTemplates" 
            :key="template.moduleType"
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
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import draggable from 'vuedraggable';
import { Plus } from '@element-plus/icons-vue';
import { allTemplates, type ModuleTemplate } from '@/resume-templates/template-definitions';
import ModuleFormItem from './forms/ModuleFormItem.vue';

const editorStore = useResumeEditorStore();
const dialogVisible = ref(false);
// 【核心新增】记录当前要添加到哪个区域
const currentAddZone = ref<'sidebar' | 'main'>('main');

const sidebarJson = computed({
  get: () => editorStore.resumeJson.sidebar,
  set: (value) => { editorStore.resumeJson.sidebar = value; },
});

const mainJson = computed({
  get: () => editorStore.resumeJson.main,
  set: (value) => { editorStore.resumeJson.main = value; },
});

const availableTemplates = computed(() => {
  const addedModuleTypes = new Set([...sidebarJson.value, ...mainJson.value].map(c => c.moduleType));
  return allTemplates.filter(t => !addedModuleTypes.has(t.moduleType));
});

// 打开弹窗时，记录目标区域
const openAddDialog = (zone: 'sidebar' | 'main') => {
    currentAddZone.value = zone;
    dialogVisible.value = true;
};

// 添加模块时，将目标区域传递给 action
const addModule = (template: ModuleTemplate) => {
  editorStore.addComponent(template.moduleType, currentAddZone.value);
  dialogVisible.value = false;
};
</script>

<style scoped>
.config-panel { padding: 16px; }
.zone-wrapper { margin-bottom: 24px; }
.zone-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.zone-title { font-size: 13px; color: #999; }
.module-list { display: flex; flex-direction: column; gap: 12px; min-height: 50px; border: 1px dashed #e0e0e0; border-radius: 4px; padding: 10px; }
.ghost { opacity: 0.5; background: #c8ebfb; border: 1px dashed #409eff; }

/* 【核心修复】恢复弹窗的美观样式 */
.module-pool {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 16px;
}
.module-pool-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 8px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}
.module-pool-item:hover {
  border-color: #409eff;
  color: #409eff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.09);
}
.module-pool-item .el-icon {
  font-size: 24px;
  margin-bottom: 8px;
}
</style>