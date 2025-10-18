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

    <div id="resume-content" class="resume-wrapper" v-else>
      <div class="resume-paper" :style="pageStyles">
        <!-- 场景一：单栏布局 -->
        <template v-if="currentLayout === 'single-column'">
          <div v-if="mainModules.length > 0" class="canvas-area">
            <!-- 直接渲染 mainModules，它在单栏模式下包含所有模块 -->
            <div v-for="element in mainModules" :key="element.id">
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
const resumeJson = ref<ResumeLayout>({ sidebar: [], main: [] }); // 存储最终用于渲染的、带有正确顺序和样式的二维数据
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

// --- 【核心重构】所有计算属性现在都依赖于本组件的 state ---

const currentTemplate = computed(() => {
  const templateId = resumeData.value?.template_name || 'default';
  return templates.find(t => t.id === templateId) || templates[0];
});

const currentLayout = computed(() => currentTemplate.value.layout);
const pageStyles = computed(() => currentTemplate.value.pageStyles || {});

// 直接从处理好的 resumeJson 中获取模块，不再进行合并操作
const sidebarModules = computed(() => resumeJson.value.sidebar.filter(m => m.props.show !== false));
const mainModules = computed(() => resumeJson.value.main.filter(m => m.props.show !== false));

// allVisibleModules 仅用于单栏布局，需要合并
const allVisibleModules = computed(() => [...sidebarModules.value, ...mainModules.value]);


onMounted(async () => {
  if (!resumeId) return;
  isLoading.value = true;
  try {
    const response = await getStructuredResumeApi(resumeId);
    resumeData.value = response;

    const template = currentTemplate.value; // 使用计算属性获取当前模板
    let finalLayout: ResumeLayout = { sidebar: [], main: [] };

    // 1. 确定原始的二维布局
    if (response.content_json && typeof response.content_json === 'object' && 'sidebar' in response.content_json) {
      finalLayout = response.content_json as ResumeLayout;
    } else if (Array.isArray(response.content_json)) {
      // 兼容旧数据：如果是数组，则全在 main
      finalLayout.main = response.content_json;
    }

    // 2. 遍历 sidebar 和 main 两个数组，为其中的每个组件应用样式和标题风格
    // 这样做可以完全保留后端返回的顺序
    const applyStyles = (components: ResumeComponent[]) => {
      components.forEach(component => {
        component.styles = template.getStylesFor(component.componentName, component.moduleType);
        if (component.componentName !== 'BaseInfoModule') {
            const templateId = template.id;
            if (templateId === 'modern-accent') component.props.titleStyle = 'style2';
            else if (templateId === 'business-gray') component.props.titleStyle = 'style3';
            else if (templateId === 'sidebar-darkblue') component.props.titleStyle = 'style4';
            else component.props.titleStyle = 'style1';
        }
      });
    };
    
    applyStyles(finalLayout.sidebar);
    applyStyles(finalLayout.main);

    // 3. 将处理好的、带有正确顺序和样式的二维数据赋值给 ref
    resumeJson.value = finalLayout;

  } catch (error) { 
    console.error(error);
    ElMessage.error('加载简历数据失败'); 
  } finally { 
    isLoading.value = false; 
  }
});

const goBack = () => {
  router.push({ name: 'ResumeEditor', params: { id: resumeId } });
};

const exportToPDF = async () => {
    // ... 导出逻辑保持不变 ...
    const resumeElement = document.querySelector('#resume-content .resume-paper');
    if (!resumeElement) { ElMessage.error('找不到简历内容，无法导出。'); return; }
    isExporting.value = true;
    try {
        const canvas = await html2canvas(resumeElement as HTMLElement, { scale: 2.5, useCORS: true, allowTaint: true, backgroundColor: '#ffffff' });
        const pdf = new jsPDF('p', 'pt', 'a4');
        const a4Width = 595.28; const a4Height = 841.89;
        const imgWidth = canvas.width; const imgHeight = canvas.height;
        const pageHeight = (imgWidth / a4Width) * a4Height;
        let position = 0;
        while (position < imgHeight) {
            const pageCanvas = document.createElement('canvas');
            pageCanvas.width = imgWidth;
            pageCanvas.height = Math.min(pageHeight, imgHeight - position);
            const ctx = pageCanvas.getContext('2d');
            if (ctx) {
                ctx.drawImage(canvas, 0, position, imgWidth, pageCanvas.height, 0, 0, imgWidth, pageCanvas.height);
                if (position > 0) pdf.addPage();
                pdf.addImage(pageCanvas.toDataURL('image/jpeg', 1.0), 'JPEG', 0, 0, a4Width, (pageCanvas.height * a4Width) / imgWidth);
            }
            position += pageHeight;
        }
        pdf.save(`简历-${resumeData.value?.title || '未命名'}.pdf`);
    } catch (error) { console.error("导出PDF失败:", error); ElMessage.error("导出PDF时发生未知错误。"); }
    finally { isExporting.value = false; }
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