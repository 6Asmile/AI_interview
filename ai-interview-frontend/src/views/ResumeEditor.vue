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
        <!-- 【核心修改】为预览按钮增加 loading 状态 -->
        <el-button @click="handlePreview" :loading="isPreviewing">预览</el-button>
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
      <aside class="editor-sidebar"><ConfigPanel /></aside>
      <main class="editor-canvas-wrapper"><ResumeCanvas /></main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import ConfigPanel from '@/components/resume/editor/ConfigPanel.vue';
import ResumeCanvas from '@/components/resume/editor/ResumeCanvas.vue';
import { SuccessFilled, ArrowLeft } from '@element-plus/icons-vue';
import { templates } from '@/resume-templates';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();
const editorStore = useResumeEditorStore();
const resumeId = Number(route.params.id);

// 【核心修改】为预览操作增加独立的 loading 状态
const isPreviewing = ref(false);

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

const handleSave = async () => {
  await editorStore.saveResume();
};

// --- 【核心修改】重写 handlePreview 函数 ---
const handlePreview = async () => {
  isPreviewing.value = true;
  try {
    // 步骤1：调用 saveResume action，但这里我们直接复用其逻辑
    if (!editorStore.resumeMeta?.id) {
      ElMessage.error("无法预览，简历ID不存在。");
      return;
    }
    const payload = {
      title: editorStore.resumeMeta.title,
      content_json: editorStore.resumeJson,
      template_name: editorStore.selectedTemplateId,
    };
    // 调用API进行静默保存
    await editorStore.saveResume();

    // 步骤2：保存成功后，再打开预览页面
    const routeData = router.resolve({ name: 'ResumePreview', params: { id: resumeId } });
    window.open(routeData.href, '_blank');

  } catch (error) {
    console.error("预览前保存失败:", error);
    ElMessage.error("数据同步失败，无法打开预览。");
  } finally {
    isPreviewing.value = false;
  }
};

const goBack = () => {
  router.push({ name: 'ResumeManagement' });
};
</script>

<style scoped>
/* 样式与之前版本完全相同，无需修改 */
.resume-editor-container { display: flex; flex-direction: column; height: calc(100vh - 60px); overflow: hidden; }
.editor-header { display: flex; justify-content: space-between; align-items: center; padding: 0 24px; height: 60px; background-color: #fff; border-bottom: 1px solid #e8e8e8; flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 16px; }
.resume-title-input { width: 300px; }
.header-actions { display: flex; align-items: center; gap: 16px; }
.template-selector { width: 150px; }
.editor-main { display: flex; flex-grow: 1; overflow: hidden; height: 100%; }
.editor-loading { padding: 20px; }
.editor-sidebar { width: 450px; background-color: #fff; border-right: 1px solid #e8e8e8; overflow-y: auto; flex-shrink: 0; height: 100%; }
.editor-canvas-wrapper { flex-grow: 1; padding: 20px; overflow-y: auto; background-color: #f0f2f5; display: flex; justify-content: center; height: 100%; }
</style>