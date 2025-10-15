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
      <div class="resume-paper" :style="pageStyles">
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
import { ref, onMounted, computed, markRaw } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import type { ResumeItem } from '@/api/modules/resume';
import type { ResumeComponent } from '@/store/modules/resumeEditor';
import { ElMessage, ElSkeleton } from 'element-plus';
import { templates } from '@/resume-templates';

// 导入所有模块组件
import BaseInfoModule from '@/components/resume/modules/BaseInfoModule.vue';
import SummaryModule from '@/components/resume/modules/SummaryModule.vue';
import EducationModule from '@/components/resume/modules/EducationModule.vue';
import WorkExpModule from '@/components/resume/modules/WorkExpModule.vue';
import ProjectModule from '@/components/resume/modules/ProjectModule.vue';
import SkillsModule from '@/components/resume/modules/SkillsModule.vue';
import GenericListModule from '@/components/resume/modules/GenericListModule.vue';
import CustomModule from '@/components/resume/modules/CustomModule.vue';

import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

const route = useRoute();
const router = useRouter();

const resumeId = Number(route.params.id);
const resumeData = ref<ResumeItem | null>(null);
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
  GenericListModule: markRaw(GenericListModule),
  CustomModule: markRaw(CustomModule),
};

const pageStyles = computed(() => {
  if (!resumeData.value?.template_name) return {};
  const currentTemplate = templates.find(t => t.id === resumeData.value!.template_name);
  return currentTemplate?.pageStyles || {};
});

onMounted(async () => {
  if (!resumeId) return;
  try {
    const response = await getStructuredResumeApi(resumeId);
    resumeData.value = response;
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

// --- 【核心修复】完善后的 PDF 导出函数 ---
const exportToPDF = async () => {
  // 1. 获取要导出内容的 DOM 元素
  const resumeElement = document.getElementById('resume-content')?.querySelector('.resume-paper');
  
  // 2. 健壮性检查
  if (!resumeElement) {
    ElMessage.error('找不到简历内容，无法导出。');
    return;
  }

  isExporting.value = true;
  try {
    // 3. 【修复#1】使用类型断言 `as HTMLElement`，解决类型不匹配问题
    const canvas = await html2canvas(resumeElement as HTMLElement, {
      scale: 2, // 提高分辨率
      useCORS: true, // 允许跨域图片
    });
    
    // 4. 【修复#2】移除未使用的 pageData 变量
    // const pageData = canvas.toDataURL('image/jpeg', 1.0); // 此行不再需要

    // 5. 定义 PDF 尺寸 (A4)
    const pdf = new jsPDF('p', 'pt', 'a4');
    const a4Width = 595.28;
    const a4Height = 841.89;
    
    // 6. 计算分页
    const imgWidth = canvas.width;
    const imgHeight = canvas.height;
    // 计算在A4宽度下，一页内容应该对应原始canvas的多少高度
    const pageHeight = (imgWidth / a4Width) * a4Height;
    let position = 0;
    
    // 7. 循环生成每一页
    while (position < imgHeight) {
      // 创建一个临时 canvas 用于截取当前页的内容
      const pageCanvas = document.createElement('canvas');
      pageCanvas.width = imgWidth;
      pageCanvas.height = Math.min(pageHeight, imgHeight - position);
      const ctx = pageCanvas.getContext('2d');
      
      if (ctx) {
        // 从主 canvas 上绘制一页的高度到临时 canvas
        ctx.drawImage(canvas, 0, position, imgWidth, pageCanvas.height, 0, 0, imgWidth, pageCanvas.height);
        
        // 如果不是第一页，需要先添加新页面
        if (position > 0) {
          pdf.addPage();
        }

        // 将临时 canvas 的内容添加到 PDF 中，并拉伸至 A4 尺寸
        pdf.addImage(pageCanvas.toDataURL('image/jpeg', 1.0), 'JPEG', 0, 0, a4Width, a4Height);
      }
      
      position += pageHeight; // 更新位置，准备截取下一页
    }
    
    pdf.save(`简历-${resumeData.value?.title || resumeId}.pdf`);
  } catch (error) {
    console.error("导出PDF失败", error);
    ElMessage.error("导出PDF时发生错误，请检查控制台。");
  } finally {
    isExporting.value = false;
  }
};
</script>

<style scoped>
/* 样式与之前版本完全相同，无需修改 */
.preview-page-container { background-color: #f0f2f5; min-height: 100vh; }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 10; }
.loading-container { max-width: 210mm; margin: 20px auto; padding: 20px; background: #fff; }
.resume-wrapper { padding: 30px 0; display: flex; justify-content: center; }
.resume-paper { width: 210mm; min-height: 297mm; background-color: #fff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); transition: all 0.3s; }
</style>