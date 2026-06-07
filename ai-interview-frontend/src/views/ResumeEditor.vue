<!-- src/views/ResumeEditor.vue -->
<template>
  <div class="resume-editor-container">
    <div class="editor-header">
      <div class="header-left">
        <el-button :icon="ArrowLeft" @click="goBack" text class="back-button">返回列表</el-button>
        <el-divider direction="vertical" />
        <el-input 
          v-if="editorStore.resumeMeta"
          v-model="editorStore.resumeMeta.title" 
          class="resume-title-input" 
          placeholder="请输入简历标题" 
        />
      </div>
      <div class="header-actions">
        <el-button @click="openJdDialog" :icon="Cpu" type="success" plain class="soft-button">AI 分析</el-button>
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
        <el-button @click="handlePreview" :loading="isPreviewing" class="soft-button">预览</el-button>
        <el-button 
          type="primary" 
          class="save-button"
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

    <el-dialog v-model="jdDialogVisible" title="AI 简历分析" width="50%" class="jd-dialog">
      <el-form-item label="请在此处粘贴目标岗位的职位描述 (JD)">
        <el-input v-model="jdText" type="textarea" :rows="10" placeholder="将职位描述粘贴到这里..." />
      </el-form-item>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="jdDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleAnalysis" :loading="isAnalyzing">
            {{ isAnalyzing ? '分析中...' : '开始分析' }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 分析报告现在通过路由跳转显示，不再需要抽屉 -->
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import ConfigPanel from '@/components/resume/editor/ConfigPanel.vue';
import ResumeCanvas from '@/components/resume/editor/ResumeCanvas.vue';
import { SuccessFilled, ArrowLeft, Cpu } from '@element-plus/icons-vue';
import { templates } from '@/resume-templates';
import { ElMessage, ElSkeleton, ElDialog, ElFormItem, ElInput, ElButton, ElDivider, ElSelect, ElOption } from 'element-plus';
import { analyzeResumeApi } from '@/api/modules/resumeEditor';

const route = useRoute();
const router = useRouter();
const editorStore = useResumeEditorStore();
const resumeId = Number(route.params.id);

const isPreviewing = ref(false);
const jdDialogVisible = ref(false);
const jdText = ref('');
const isAnalyzing = ref(false);

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

const handlePreview = async () => {
  isPreviewing.value = true;
  try {
    await editorStore.saveResume();
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

const openJdDialog = () => {
  jdDialogVisible.value = true;
};

const handleAnalysis = async () => {
  if (!jdText.value.trim()) {
    ElMessage.warning('职位描述不能为空');
    return;
  }
  isAnalyzing.value = true;
  try {
    const newReport = await analyzeResumeApi(resumeId, jdText.value);
    jdDialogVisible.value = false;
    ElMessage.success('分析完成，正在跳转到报告页面...');
    router.push({ name: 'AnalysisReportDetail', params: { reportId: newReport.id } });
  } catch (error) {
    // 错误已由 axios 拦截器处理
  } finally {
    isAnalyzing.value = false;
  }
};
</script>

<style scoped>
.resume-editor-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(80, 140, 255, 0.1), transparent 24%),
    linear-gradient(180deg, #f7faff 0%, #eef3fb 100%);
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 72px;
  background: rgba(255, 255, 255, 0.88);
  border-bottom: 1px solid #e1e9f5;
  box-shadow: 0 10px 30px rgba(56, 83, 126, 0.06);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-button {
  color: #5872a0;
  font-weight: 600;
}

.resume-title-input {
  width: 340px;
}

.resume-title-input :deep(.el-input__wrapper) {
  border-radius: 14px;
  box-shadow: 0 0 0 1px #dbe4f2 inset;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.template-selector {
  width: 170px;
}

.template-selector :deep(.el-select__wrapper) {
  border-radius: 14px;
}

.soft-button {
  border-radius: 14px;
}

.save-button {
  min-height: 44px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 16px 28px rgba(42, 101, 216, 0.18);
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
  background: rgba(255, 255, 255, 0.88);
  border-right: 1px solid #e3eaf6;
  overflow-y: auto;
  flex-shrink: 0;
  height: 100%;
  box-shadow: 8px 0 24px rgba(56, 83, 126, 0.04);
}

.editor-canvas-wrapper {
  flex-grow: 1;
  padding: 26px;
  overflow-y: auto;
  display: flex;
  justify-content: center;
  height: 100%;
}

:deep(.jd-dialog .el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

:deep(.jd-dialog .el-dialog__header) {
  padding: 22px 24px 18px;
  margin-right: 0;
  border-bottom: 1px solid #edf1f8;
}

:deep(.jd-dialog .el-dialog__body) {
  padding: 24px;
}

@media (max-width: 1100px) {
  .editor-header {
    height: auto;
    padding: 16px 20px;
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .resume-title-input {
    width: 240px;
  }
}
</style>
