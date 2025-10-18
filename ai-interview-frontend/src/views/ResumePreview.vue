<!-- src/views/ResumePreview.vue -->
<template>
  <div class="preview-page-container">
    <div class="preview-header">
      <h1>简历预览</h1>
      <div class="actions">
        <el-button @click="goBack">返回编辑</el-button>
        <el-button type="primary" @click="exportToPDF" :loading="isExporting" :icon="Download">
          {{ isExporting ? '导出中...' : '导出为 PDF' }}
        </el-button>
      </div>
    </div>

    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <!-- #resume-content 是 html2canvas 的目标 -->
    <div id="resume-content" class="resume-wrapper" v-else>
      <div class="resume-paper" :style="pageStyles">
        <!-- 场景一：单栏布局 -->
        <template v-if="currentLayout === 'single-column'">
          <div v-if="allVisibleModules.length > 0" class="canvas-area">
            <div v-for="element in allVisibleModules" :key="element.id">
              <component :is="componentMap[element.componentName]" v-bind="element.props" :style="element.styles" />
            </div>
          </div>
          <div v-else class="empty-tip"><el-empty description="该简历暂无内容" /></div>
        </template>
        
        <!-- 场景二：左右分栏布局 -->
        <SidebarLayout v-if="currentLayout === 'sidebar'">
          <template #sidebar>
            <div v-for="element in sidebarModules" :key="element.id">
              <component :is="componentMap[element.componentName]" v-bind="element.props" :style="element.styles" />
            </div>
          </template>
          <template #main>
            <div v-for="element in mainModules" :key="element.id">
              <component :is="componentMap[element.componentName]" v-bind="element.props" :style="element.styles" />
            </div>
          </template>
        </SidebarLayout>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, markRaw } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import type { ResumeItem } from '@/api/modules/resume';
import { type ResumeComponent, type ResumeLayout } from '@/store/modules/resumeEditor';
import { ElMessage, ElSkeleton, ElEmpty } from 'element-plus';
import { Download } from '@element-plus/icons-vue';
import { templates } from '@/resume-templates';

// 导入所有需要的组件
import SidebarLayout from '@/components/resume/layouts/SidebarLayout.vue';
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
const resumeJson = ref<ResumeLayout>({ sidebar: [], main: [] });
const isLoading = ref(true);
const isExporting = ref(false);

// --- 【核心修复#1】确保 computed 属性从本组件的 ref 中读取数据 ---
const currentTemplate = computed(() => {
  const templateId = resumeData.value?.template_name || 'default';
  return templates.find(t => t.id === templateId) || templates[0];
});
const currentLayout = computed(() => currentTemplate.value.layout);
const pageStyles = computed(() => currentTemplate.value.pageStyles || {});

const allModules = computed(() => [...resumeJson.value.sidebar, ...resumeJson.value.main]);
const allVisibleModules = computed(() => allModules.value.filter((m: ResumeComponent) => m.props.show !== false));
const sidebarModules = computed(() => allVisibleModules.value.filter((m: ResumeComponent) => m.props.layoutZone === 'sidebar'));
const mainModules = computed(() => allVisibleModules.value.filter((m: ResumeComponent) => m.props.layoutZone !== 'sidebar'));

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

onMounted(async () => {
  if (!resumeId) return;
  isLoading.value = true;
  try {
    const response = await getStructuredResumeApi(resumeId);
    resumeData.value = response;
    // 适配后端可能返回的一维或二维 content_json
    if (response.content_json && typeof response.content_json === 'object' && 'sidebar' in response.content_json && 'main' in response.content_json) {
      resumeJson.value = response.content_json as ResumeLayout;
    } else if (Array.isArray(response.content_json)) {
      // 如果是旧的一维数组，根据模板布局进行分配
      const template = templates.find(t => t.id === response.template_name) || templates[0];
      if (template.layout === 'sidebar') {
        const sidebar: ResumeComponent[] = [];
        const main: ResumeComponent[] = [];
        response.content_json.forEach(comp => {
            if (['BaseInfo', 'Skills'].includes(comp.moduleType)) sidebar.push(comp);
            else main.push(comp);
        });
        resumeJson.value = { sidebar, main };
      } else {
        resumeJson.value = { sidebar: [], main: response.content_json };
      }
    }
  } catch (error) { 
    ElMessage.error('加载简历数据失败'); 
  } finally { 
    isLoading.value = false; 
  }
});

const goBack = () => {
  router.push({ name: 'ResumeEditor', params: { id: resumeId } });
};

// --- 【核心修复#2】加固 PDF 导出函数 ---
const exportToPDF = async () => {
  // 确保在 DOM 更新后再执行
  await router.isReady();

  const resumeElement = document.querySelector('#resume-content .resume-paper');
  if (!resumeElement) {
    ElMessage.error('找不到简历内容元素，无法导出。');
    return;
  }

  isExporting.value = true;
  try {
    const canvas = await html2canvas(resumeElement as HTMLElement, {
      scale: 2.5, // 进一步提高分辨率以获得更清晰的文本
      useCORS: true,
      allowTaint: true, // 允许绘制跨域图片
      backgroundColor: '#ffffff', // 明确背景色
    });
    
    const pdf = new jsPDF('p', 'pt', 'a4');
    const a4Width = 595.28;
    const a4Height = 841.89;
    const imgWidth = canvas.width;
    const imgHeight = canvas.height;
    const pageData = canvas.toDataURL('image/jpeg', 1.0);

    // 计算内容在A4纸上应该有的高度
    const pdfPageHeight = (imgWidth / a4Width) * a4Height;
    let position = 0;

    while (position < imgHeight) {
      // 创建一个临时 canvas 用于截取当前页的内容
      const pageCanvas = document.createElement('canvas');
      pageCanvas.width = imgWidth;
      // 截取的高度不能超过剩余内容的高度
      pageCanvas.height = Math.min(pdfPageHeight, imgHeight - position);
      const ctx = pageCanvas.getContext('2d');
      
      if (ctx) {
        // 从主 canvas 上绘制一页的高度到临时 canvas
        ctx.drawImage(canvas, 0, position, imgWidth, pageCanvas.height, 0, 0, imgWidth, pageCanvas.height);
        
        if (position > 0) {
          pdf.addPage();
        }
        // 将临时 canvas 的内容添加到 PDF 中
        pdf.addImage(
          pageCanvas.toDataURL('image/jpeg', 1.0),
          'JPEG',
          0,
          0,
          a4Width,
          (pageCanvas.height * a4Width) / imgWidth // 按比例计算图片在PDF中的高度
        );
      }
      
      position += pdfPageHeight;
    }
    
    pdf.save(`简历-${resumeData.value?.title || '未命名'}.pdf`);
  } catch (error) {
    console.error("导出PDF失败:", error);
    ElMessage.error("导出PDF时发生未知错误，请检查控制台。");
  } finally {
    isExporting.value = false;
  }
};
</script>

<style scoped>
.preview-page-container { background-color: #f0f2f5; min-height: 100vh; }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background-color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 10; }
.loading-container { max-width: 210mm; margin: 20px auto; padding: 20px; background: #fff; }
.resume-wrapper { padding: 30px 0; display: flex; justify-content: center; }
.resume-paper { width: 210mm; min-height: 297mm; background-color: #fff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); transition: all 0.3s; }
.empty-tip { padding-top: 100px; }
</style>