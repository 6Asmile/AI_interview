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
import { ref, computed, watch, nextTick } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import draggable from 'vuedraggable';
import { Plus } from '@element-plus/icons-vue';
import { allTemplates, type ModuleTemplate } from '@/resume-templates/template-definitions';
import ModuleFormItem from './forms/ModuleFormItem.vue';

const editorStore = useResumeEditorStore();
const dialogVisible = ref(false);
const currentAddZone = ref<'sidebar' | 'main'>('main');

// computed for sidebar modules
const sidebarJson = computed({
  get: () => editorStore.resumeJson.sidebar,
  set: (value) => { editorStore.resumeJson.sidebar = value; },
});

// computed for main content modules
const mainJson = computed({
  get: () => editorStore.resumeJson.main,
  set: (value) => { editorStore.resumeJson.main = value; },
});

const availableTemplates = computed(() => {
  const addedModuleTypes = new Set([...sidebarJson.value, ...mainJson.value].map(c => c.moduleType));
  return allTemplates.filter(t => !addedModuleTypes.has(t.moduleType));
});

const openAddDialog = (zone: 'sidebar' | 'main') => {
    currentAddZone.value = zone;
    dialogVisible.value = true;
};

const addModule = (template: ModuleTemplate) => {
  editorStore.addComponent(template.moduleType, currentAddZone.value);
  dialogVisible.value = false;
  // Auto-scroll to the newly added module after DOM update
  nextTick(() => {
    const targetArray = currentAddZone.value === 'sidebar' ? sidebarJson.value : mainJson.value;
    const newModule = targetArray[targetArray.length - 1];
    if (newModule) {
      // Set as selected and scroll
      editorStore.selectComponent(newModule.id);
      scrollToConfigModule(newModule.id);
    }
  });
};

const scrollToConfigModule = (moduleId: string) => {
    nextTick(() => {
        const targetId = `config-module-header-${moduleId}`;
        const targetElement = document.getElementById(targetId);
        if (targetElement) {
            targetElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
            });
        }
    });
};

// Watch for changes from the canvas click
watch(() => editorStore.selectedComponentId, (newId) => {
    if (newId) {
        scrollToConfigModule(newId);
    }
});
</script>

<style scoped>
.config-panel {
  padding: 16px;
}
.zone-wrapper {
  margin-bottom: 24px;
}
.zone-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.zone-title {
  font-size: 13px;
  color: #999;
}
.module-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 50px;
  border: 1px dashed #e0e0e0;
  border-radius: 4px;
  padding: 10px;
}
.ghost {
  opacity: 0.5;
  background: #c8ebfb;
  border: 1px dashed #409eff;
}
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