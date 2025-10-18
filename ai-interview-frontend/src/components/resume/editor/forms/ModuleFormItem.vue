<!-- src/components/resume/editor/forms/ModuleFormItem.vue -->
<template>
  <el-collapse v-model="activeName" class="module-form" @change="handleCollapseChange">
    <el-collapse-item :name="module.id">
      <template #title>
        <div class="module-header">
          <el-icon class="drag-handle"><Rank /></el-icon>
          <span class="module-title">{{ module.title }}</span>
          <div class="header-actions">
            <el-switch v-model="module.props.show" size="small" @click.stop />
            <el-button link type="danger" :icon="Delete" @click.stop="confirmDelete" />
          </div>
        </div>
      </template>
      <div class="module-content">
        <!-- 表单渲染逻辑 -->
        <BaseInfoForm v-if="module.componentName === 'BaseInfoModule'" :module="module" />
        <WorkExpForm v-else-if="module.componentName === 'WorkExpModule'" :module="module" propKey="experiences" />
        <GenericListForm v-else-if="module.componentName === 'EducationModule'" :module="module" propKey="educations" />
        <GenericListForm v-else-if="module.componentName === 'ProjectModule'" :module="module" propKey="projects" />
        <GenericListForm v-else-if="module.componentName === 'SkillsModule'" :module="module" propKey="skills" />
        <GenericListForm v-else-if="module.componentName === 'GenericListModule'" :module="module" propKey="items" />
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
    ElMessageBox.confirm(`确定删除“${props.module.title}”？`, '提示', { type: 'warning' })
        .then(() => editorStore.deleteComponent(props.module.id));
};
</script>

<style scoped>
.module-form { border: 1px solid #e8e8e8; border-radius: 4px; overflow: hidden; }
.module-header { display: flex; align-items: center; width: 100%; padding: 0 15px; }
.drag-handle { cursor: grab; color: #999; margin-right: 10px; }
.module-title { font-weight: 500; flex-grow: 1; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.module-content { padding: 0 15px 15px; }
:deep(.el-collapse-item__header) { padding: 0; height: 48px; background-color: #fafafa; }
:deep(.el-collapse-item__wrap) { border-bottom: none; }
:deep(.el-collapse-item__content) { padding-bottom: 0; }
</style>