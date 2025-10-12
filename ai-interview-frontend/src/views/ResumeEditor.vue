<!-- src/views/ResumeEditor.vue -->
<template>
  <div class="resume-editor-container">
    <div class="editor-header">
      <h1>在线简历编辑器</h1>
      <div class="header-actions">
        <!-- 模板选择器 -->
        <el-select 
          v-model="selectedTemplateId" 
          placeholder="选择模板"
          class="template-selector"
        >
          <el-option
            v-for="template in templates"
            :key="template.id"
            :label="template.name"
            :value="template.id"
          />
        </el-select>

        <el-button @click="goBack">返回</el-button>
        <el-button @click="handlePreview">预览</el-button>
        <el-button 
          type="primary" 
          @click="handleSave" 
          :loading="editorStore.isSaving"
          :icon="SuccessFilled"
        >
          {{ editorStore.isSaving ? '保存中...' : '保存简历' }}
        </el-button>
      </div>
    </div>
    
    <div v-if="editorStore.isLoading" class="editor-loading">
      <el-skeleton :rows="10" animated />
    </div>
    
    <div v-else class="editor-main">
      <!-- 左侧：组件库 -->
      <aside class="editor-sidebar editor-sidebar-left">
        <ComponentLibrary />
      </aside>
      
      <!-- 中间：画布 -->
      <main class="editor-canvas-wrapper">
        <ResumeCanvas />
      </main>
      
      <!-- 右侧：配置面板 -->
      <aside class="editor-sidebar editor-sidebar-right">
        <ConfigPanel />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import ComponentLibrary from '@/components/resume/editor/ComponentLibrary.vue';
import ResumeCanvas from '@/components/resume/editor/ResumeCanvas.vue';
import ConfigPanel from '@/components/resume/editor/ConfigPanel.vue';
import { SuccessFilled } from '@element-plus/icons-vue';
import { templates } from '@/resume-templates';

const route = useRoute();
const router = useRouter();
const editorStore = useResumeEditorStore();

const resumeId = Number(route.params.id);

// 组件挂载时，加载简历数据
onMounted(() => {
  if (resumeId) {
    editorStore.fetchResume(resumeId);
  }
});

// 使用 computed 实现模板选择器与 Store 的双向绑定
const selectedTemplateId = computed({
  get: () => editorStore.selectedTemplateId,
  set: (val) => {
    // 当用户选择新模板时，调用 action
    if (val) editorStore.applyTemplate(val);
  },
});

// 处理保存
const handleSave = () => {
  editorStore.saveResume();
};

// 处理预览
const handlePreview = () => {
  const routeData = router.resolve({ name: 'ResumePreview', params: { id: resumeId } });
  window.open(routeData.href, '_blank');
};

// 返回上一页
const goBack = () => {
  router.push({ name: 'ResumeManagement' });
};
</script>

<style scoped>
.resume-editor-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px); /* 减去顶部导航栏的高度 */
  background-color: #f0f2f5;
  overflow: hidden;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 60px;
  background-color: #fff;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.editor-header h1 {
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.template-selector {
  width: 150px;
}

.editor-main {
  display: flex;
  flex-grow: 1;
  overflow: hidden;
  height: 100%;
}

.editor-loading {
  padding: 20px;
}

.editor-sidebar {
  width: 280px;
  background-color: #fff;
  padding: 16px;
  overflow-y: auto;
  flex-shrink: 0;
  height: 100%;
}

.editor-sidebar-left {
  border-right: 1px solid #e8e8e8;
}
.editor-sidebar-right {
  border-left: 1px solid #e8e8e8;
}

.editor-canvas-wrapper {
  flex-grow: 1;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  justify-content: center;
  height: 100%;
}
</style>