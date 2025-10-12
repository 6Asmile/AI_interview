<!-- src/views/ResumePreview.vue -->
<template>
  <div class="preview-page-container">
    <div class="preview-header">
      <h1>简历预览</h1>
      <div class="actions">
        <el-button @click="goBack">返回编辑</el-button>
        <el-button type="primary" @click="exportToPDF" :loading="isExporting">
          {{ isExporting ? '导出中...' : '导出为 PDF' }}
        </el-button>
      </div>
    </div>

    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <div id="resume-content" class="resume-wrapper" v-else>
      <div class="resume-paper">
        <div v-for="component in resumeJson" :key="component.id">
          <component
            :is="componentMap[component.componentName]"
            v-bind="component.props"
            :style="component.styles"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 【修复#1】移除未使用的 'computed'
import { ref, onMounted, markRaw } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
// 【修复#2】从 store 中导入我们刚刚导出的 ResumeComponent 类型
import type { ResumeComponent } from '@/store/modules/resumeEditor';
import { ElMessage } from 'element-plus';

import BaseInfoModule from '@/components/resume/modules/BaseInfoModule.vue';
import SummaryModule from '@/components/resume/modules/SummaryModule.vue';
import EducationModule from '@/components/resume/modules/EducationModule.vue';
import WorkExpModule from '@/components/resume/modules/WorkExpModule.vue';
import ProjectModule from '@/components/resume/modules/ProjectModule.vue';
import SkillsModule from '@/components/resume/modules/SkillsModule.vue';

import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

const route = useRoute();
const router = useRouter();

const resumeId = Number(route.params.id);
const resumeJson = ref<ResumeComponent[]>([]);
const isLoading = ref(true);
const isExporting = ref(false);

const componentMap: Record<string, any> = {
  BaseInfoModule: markRaw(BaseInfoModule),
  SummaryModule: markRaw(SummaryModule),
  EducationModule: markRaw(EducationModule),
  WorkExpModule: markRaw(WorkExpModule),
  ProjectModule: markRaw(ProjectModule),
  SkillsModule: markRaw(SkillsModule),
};

onMounted(async () => {
  if (!resumeId) return;
  try {
    const response = await getStructuredResumeApi(resumeId);
    resumeJson.value = Array.isArray(response.content_json) ? response.content_json : [];
  } catch (error) {
    ElMessage.error('加载简历数据失败');
  } finally {
    isLoading.value = false;
  }
});

const goBack = () => {
  router.push({ name: 'ResumeEditor', params: { id: resumeId } });
};

const exportToPDF = async () => {
  const resumeElement = document.getElementById('resume-content');
  if (!resumeElement) return;

  isExporting.value = true;
  try {
    const canvas = await html2canvas(resumeElement, {
      scale: 2,
      useCORS: true,
      backgroundColor: null,
    });
    
    const pageData = canvas.toDataURL('image/jpeg', 1.0);
    
    const a4Width = 595.28;
    const a4Height = 841.89;

    const contentWidth = canvas.width;
    const contentHeight = canvas.height;

    const pdfHeight = (contentHeight * a4Width) / contentWidth;
    const pdfWidth = a4Width;

    let position = 0;
    // 【优化】使用 contentHeight 而不是 pdfHeight 进行分页判断
    const pageHeight = (contentWidth / a4Width) * a4Height;
    const pdf = new jsPDF('p', 'pt', 'a4');

    if (contentHeight < pageHeight) {
      pdf.addImage(pageData, 'JPEG', 0, 0, pdfWidth, pdfHeight);
    } else {
      while (position < contentHeight) {
        // 截取一页的内容
        const pageCanvas = document.createElement('canvas');
        pageCanvas.width = contentWidth;
        pageCanvas.height = Math.min(pageHeight, contentHeight - position);
        const ctx = pageCanvas.getContext('2d');
        if (ctx) {
            ctx.drawImage(canvas, 0, position, contentWidth, pageCanvas.height, 0, 0, contentWidth, pageCanvas.height);
            pdf.addImage(pageCanvas.toDataURL('image/jpeg', 1.0), 'JPEG', 0, 0, a4Width, a4Height);
        }
        
        position += pageHeight;
        if (position < contentHeight) {
          pdf.addPage();
        }
      }
    }
    
    pdf.save('我的简历.pdf');
  } catch (error) {
    console.error("导出PDF失败", error);
    ElMessage.error("导出PDF失败，请稍后重试。");
  } finally {
    isExporting.value = false;
  }
};
</script>

<style scoped>
/* 样式与之前保持一致，无需修改 */
.preview-page-container { background-color: #f0f2f5; min-height: 100vh; }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 10; }
.loading-container { max-width: 210mm; margin: 20px auto; padding: 20px; background: #fff; }
.resume-wrapper { padding: 30px 0; display: flex; justify-content: center; }
.resume-paper { width: 210mm; min-height: 297mm; background-color: #fff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }
</style>