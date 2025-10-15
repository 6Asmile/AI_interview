<!-- src/views/ResumeEditor.vue -->
<template>
  <div class="resume-editor-container">
    <div class="editor-header">
      <div class="header-left">
        <el-button :icon="ArrowLeft" @click="goBack" text>返回列表</el-button>
        <el-divider direction="vertical" />
        <el-input 
          v-if="editorStore.resumeMeta"
          v-model="editorStore.resumeMeta.title" 
          class="resume-title-input" 
          placeholder="请输入简历标题" 
        />
      </div>
      <div class="header-actions">
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
      <aside class="editor-sidebar">
        <ConfigPanel />
      </aside>
      <main class="editor-canvas-wrapper">
        <ResumeCanvas />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import ConfigPanel from '@/components/resume/editor/ConfigPanel.vue';
import ResumeCanvas from '@/components/resume/editor/ResumeCanvas.vue';
import { SuccessFilled, ArrowLeft } from '@element-plus/icons-vue';
import { templates } from '@/resume-templates';

const route = useRoute();
const router = useRouter();
const editorStore = useResumeEditorStore();
const resumeId = Number(route.params.id);

onMounted(() => {
  if (resumeId) {
    editorStore.fetchResume(resumeId);
  }
});

const selectedTemplateId = computed({
  get: () => editorStore.selectedTemplateId,
  set: (val) => {
    if (val) {
      editorStore.applyTemplate(val);
    }
  },
});

const handleSave = () => {
  editorStore.saveResume();
};

const handlePreview = () => {
  const routeData = router.resolve({ name: 'ResumePreview', params: { id: resumeId } });
  window.open(routeData.href, '_blank');
};

const goBack = () => {
  router.push({ name: 'ResumeManagement' });
};
</script>

<style scoped>
.resume-editor-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
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
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.resume-title-input {
  width: 300px;
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
  width: 450px;
  background-color: #fff;
  border-right: 1px solid #e8e8e8;
  overflow-y: auto;
  flex-shrink: 0;
  height: 100%;
}
.editor-canvas-wrapper {
  flex-grow: 1;
  padding: 20px;
  overflow-y: auto;
  background-color: #f0f2f5;
  display: flex;
  justify-content: center;
  height: 100%;
}
</style>