<!-- src/components/resume/editor/forms/ModuleFormItem.vue -->
<template>
  <el-collapse v-model="activeName" class="module-form" @change="handleCollapseChange">
    <el-collapse-item :name="module.id">
      <template #title>
        <!-- 【核心修复】将 header 设为插槽的唯一子元素 -->
        <div class="module-header" :id="`config-module-header-${module.id}`">
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
              @click.stop="confirmDelete"
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

<script setup lang="ts">
import { ref } from 'vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import { Rank, Delete } from '@element-plus/icons-vue';
import { ElMessageBox } from 'element-plus';
import BaseInfoForm from './BaseInfoForm.vue';
import WorkExpForm from './WorkExpForm.vue';
import GenericListForm from './GenericListForm.vue';

const props = defineProps<{ module: any }>();
const editorStore = useResumeEditorStore();
const activeName = ref<string>('');

const handleCollapseChange = (name: string | string[]) => {
  const newActiveId = Array.isArray(name) ? name[0] : name;
  activeName.value = newActiveId;
  editorStore.selectComponent(newActiveId || null);
};

const confirmDelete = () => {
    ElMessageBox.confirm(`确定要删除“${props.module.title}”？`, '提示', { type: 'warning' })
        .then(() => editorStore.deleteComponent(props.module.id));
};

const handleSimpleModuleInput = (module: any, value: string) => {
    if (module.props.hasOwnProperty('summary')) {
        module.props.summary = value;
    } else if (module.props.hasOwnProperty('content')) {
        module.props.content = value;
    }
};
</script>

<style scoped>
.module-form {
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  overflow: hidden;
  --el-collapse-border-color: transparent;
}

/* --- 【核心修复】 --- */
/* 1. 使用 :deep() 选择器强制 el-collapse-item__header 成为 Flex 容器 */
:deep(.el-collapse-item__header) {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 0;
  height: 48px;
  background-color: #fafafa;
}

/* 2. 确保我们的 .module-header 能撑满这个 Flex 容器 */
.module-header {
  display: flex;
  align-items: center;
  flex-grow: 1; /* 让它占据整个 header 宽度 */
  padding: 0 15px;
}

/* 3. 沿用之前的 Flex 布局逻辑 */
.drag-handle {
  cursor: grab;
  color: #999;
  margin-right: 10px;
}
.module-title {
  font-weight: 500;
  flex-grow: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px; 
  flex-shrink: 0;
}
/* -------------------- */

.module-content {
  padding: 0 15px 15px;
}
:deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
:deep(.el-collapse-item__content) {
  padding-bottom: 0;
}
</style>