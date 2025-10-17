<!-- src/components/resume/editor/ConfigPanel.vue -->
<template>
  <div class="config-panel">
    <draggable
      v-model="resumeJson"
      item-key="id"
      handle=".drag-handle"
      class="module-list"
      ghost-class="ghost"
    >
      <template #item="{ element: module }">
        <el-collapse v-model="activeCollapseNames" class="module-form" @change="handleCollapseChange">
          <el-collapse-item :name="module.id">
            <template #title>
              <div class="module-header">
                <el-icon class="drag-handle"><Rank /></el-icon>
                <span class="module-title">{{ module.title }}</span>
                <div class="header-actions">
                  <el-switch
                    v-model="module.props.show"
                    size="small"
                    @click.stop
                  />
                  <el-button
                    link
                    type="danger"
                    :icon="Delete"
                    @click.stop="confirmDelete(module.id, module.title)"
                  />
                </div>
              </div>
            </template>
            
            <div class="module-content">
              <BaseInfoForm v-if="module.componentName === 'BaseInfoModule'" :module="module" />
              <WorkExpForm v-else-if="module.componentName === 'WorkExpModule'" :module="module" propKey="experiences" />
              <GenericListForm v-else-if="module.componentName === 'EducationModule'" :module="module" propKey="educations" />
              <GenericListForm v-else-if="module.componentName === 'ProjectModule'" :module="module" propKey="projects" />
              <GenericListForm v-else-if="module.componentName === 'SkillsModule'" :module="module" propKey="skills" />
              <GenericListForm v-else-if="module.componentName === 'GenericListModule'" :module="module" propKey="items" />
              <el-form v-else-if="module.componentName === 'SummaryModule' || module.componentName === 'CustomModule'" label-position="top">
                <el-form-item :label="module.title">
                   <el-input
                    type="textarea"
                    autosize
                    :model-value="module.props.summary || module.props.content"
                    @input="(value: string) => handleSimpleModuleInput(module, value)"
                  />
                </el-form-item>
              </el-form>
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
    </draggable>

    <div class="add-module-container">
      <el-button @click="dialogVisible = true" :icon="Plus" type="primary" plain>添加模块</el-button>
    </div>
    
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
import { ref, computed, nextTick } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import draggable from 'vuedraggable';
import { Rank, Delete, Plus } from '@element-plus/icons-vue';
import { allTemplates, type ModuleTemplate } from '@/resume-templates/template-definitions';
import { ElMessageBox } from 'element-plus';
import BaseInfoForm from './forms/BaseInfoForm.vue';
import WorkExpForm from './forms/WorkExpForm.vue';
import GenericListForm from './forms/GenericListForm.vue';

const editorStore = useResumeEditorStore();
const activeCollapseNames = ref<string[]>([]);
const dialogVisible = ref(false);

const resumeJson = computed({
  get: () => editorStore.resumeJson,
  set: (value) => editorStore.updateResumeJson(value),
});

const availableTemplates = computed(() => {
  const addedModuleTypes = new Set(editorStore.resumeJson.map(c => c.moduleType));
  return allTemplates.filter(t => !addedModuleTypes.has(t.moduleType));
});

const addModule = (template: ModuleTemplate) => {
  editorStore.addComponent(template.moduleType);
  dialogVisible.value = false;
  nextTick(() => {
    const newModule = resumeJson.value[resumeJson.value.length - 1];
    if (newModule && !activeCollapseNames.value.includes(newModule.id)) {
        activeCollapseNames.value.push(newModule.id);
    }
  });
};

const handleSimpleModuleInput = (module: any, value: string) => {
    if (module.props.hasOwnProperty('summary')) {
        module.props.summary = value;
    } else if (module.props.hasOwnProperty('content')) {
        module.props.content = value;
    }
};

const confirmDelete = (moduleId: string, moduleTitle: string) => {
    ElMessageBox.confirm(`确定要删除“${moduleTitle}”模块吗？`, '提示', {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
    }).then(() => {
        editorStore.deleteComponent(moduleId);
    }).catch(() => {});
};

const handleCollapseChange = (names: string[]) => {
    activeCollapseNames.value = names;
};
</script>

<style scoped>
.config-panel { padding: 16px; }
.module-list { display: flex; flex-direction: column; gap: 12px; }
.module-form { border: 1px solid #e8e8e8; border-radius: 4px; overflow: hidden; }
.ghost { opacity: 0.5; background: #c8ebfb; border: 1px dashed #409eff; }
.module-header { display: flex; align-items: center; width: 100%; padding: 0 15px; }
.drag-handle { cursor: grab; color: #999; margin-right: 10px; }
.module-title { font-weight: 500; flex-grow: 1; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.module-content { padding: 0 15px 15px; }
.config-panel :deep(.el-collapse-item__header) { padding: 0; height: 48px; background-color: #fafafa; }
.config-panel :deep(.el-collapse-item__wrap) { border-bottom: none; }
.config-panel :deep(.el-collapse-item__content) { padding-bottom: 0; }
.add-module-container { margin-top: 20px; text-align: center; }
.module-pool { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 16px; }
.module-pool-item { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 16px 8px; border: 1px solid #e8e8e8; border-radius: 4px; cursor: pointer; }
.module-pool-item:hover { border-color: #409eff; color: #409eff; }
.module-pool-item .el-icon { font-size: 24px; margin-bottom: 8px; }
</style>