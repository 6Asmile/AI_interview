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
        <el-button @click="openJdDialog" :icon="Cpu" type="success" plain>AI 分析</el-button>
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

    <el-dialog v-model="jdDialogVisible" title="AI 简历分析" width="50%">
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

    <!-- 【核心修复】移除对旧抽屉组件的所有引用 -->
    <!-- <AnalysisReportDrawer :visible="reportDrawerVisible" :report="analysisReport" @close="reportDrawerVisible = false" /> -->
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
// 【核心修复】移除未使用的 AnalysisReport 导入
import { analyzeResumeApi } from '@/api/modules/resumeEditor';
// 【核心修复】移除未使用的 AnalysisReportDrawer 导入
// import AnalysisReportDrawer from '@/components/resume/analysis/AnalysisReportDrawer.vue';

const route = useRoute();
const router = useRouter();
const editorStore = useResumeEditorStore();
const resumeId = Number(route.params.id);

const isPreviewing = ref(false);

// AI 分析相关状态
const jdDialogVisible = ref(false);
const jdText = ref('');
const isAnalyzing = ref(false);
// 【核心修复】移除不再需要的 ref
// const reportDrawerVisible = ref(false);
// const analysisReport = ref<AnalysisReport | null>(null);

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
    // 【核心修复】现在 newReport 的类型是 ResumeAnalysisReportItem，它有 'id' 属性
    router.push({ name: 'AnalysisReportDetail', params: { reportId: newReport.id } });
  } catch (error) {
    // 错误已由 axios 拦截器处理
  } finally {
    isAnalyzing.value = false;
  }
};
</script>

<style scoped>
/* 样式与之前版本完全相同 */
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