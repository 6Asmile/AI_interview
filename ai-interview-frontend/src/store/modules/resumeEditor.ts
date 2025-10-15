// src/store/modules/resumeEditor.ts
import { defineStore } from 'pinia';
import { v4 as uuidv4 } from 'uuid';
// 【修复#1】修正 API 函数的导入来源
import { updateResumeApi, type ResumeItem } from '@/api/modules/resume';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import { ElMessage } from 'element-plus';
import { templates } from '@/resume-templates';
// 【修复#2】从我们新创建的文件中导入模块定义
import { allTemplates } from '@/resume-templates/template-definitions';

// 接口定义...
export interface ResumeComponent {
  id: string;
  componentName: string;
  moduleType: string; // 【新增】
  title: string;
  props: Record<string, any>;
  styles: Record<string, any>;
}

interface FullResumeItem extends ResumeItem {
  template_name?: string;
}

interface ResumeEditorState {
  resumeMeta: FullResumeItem | null;
  resumeJson: ResumeComponent[];
  selectedTemplateId: string;
  isLoading: boolean;
  isSaving: boolean;
}

export const useResumeEditorStore = defineStore('resumeEditor', {
  state: (): ResumeEditorState => ({
    resumeMeta: null,
    resumeJson: [],
    selectedTemplateId: 'professional-darkblue',
    isLoading: false,
    isSaving: false,
  }),

  // getters 保持不变

  actions: {
    // fetchResume, saveResume, resetState 保持不变
    async fetchResume(resumeId: number) {
      this.isLoading = true;
      this.resetState();
      try {
        const response = await getStructuredResumeApi(resumeId);
        this.resumeMeta = response;
        this.resumeJson = Array.isArray(response.content_json) ? response.content_json : [];
        this.selectedTemplateId = response.template_name || 'professional-darkblue';
      } catch (error) { console.error(error); ElMessage.error("加载简历数据失败"); } 
      finally { this.isLoading = false; }
    },
    async saveResume() {
      if (!this.resumeMeta?.id) return;
      this.isSaving = true;
      try {
        const payload: Partial<FullResumeItem> = {
          title: this.resumeMeta.title,
          content_json: this.resumeJson,
          template_name: this.selectedTemplateId,
        };
        await updateResumeApi(this.resumeMeta.id, payload);
        ElMessage.success('简历已成功保存！');
      } catch (error) { console.error(error); ElMessage.error("保存失败"); } 
      finally { this.isSaving = false; }
    },
    resetState() {
      this.resumeMeta = null;
      this.resumeJson = [];
      this.selectedTemplateId = 'professional-darkblue';
    },

    applyTemplate(templateId: string) {
      const template = templates.find(t => t.id === templateId);
      if (!template) return;
      this.selectedTemplateId = templateId;
      this.resumeJson.forEach(component => {
        component.styles = template.getStylesFor(component.componentName);
      });
    },

    updateResumeJson(newJson: ResumeComponent[]) {
      this.resumeJson = newJson;
    },

    addComponent(moduleType: string) {
      // 【修复#3】因为 allTemplates 现在有明确类型，所以 't' 不再是 any
      const template = allTemplates.find(t => t.componentName === moduleType);
      if (!template) return;

      const propsCopy = JSON.parse(JSON.stringify(template.props));
      // 为列表项生成ID
      Object.keys(propsCopy).forEach(key => {
        if (Array.isArray(propsCopy[key])) {
          (propsCopy[key] as any[]).forEach((item: any) => item.id = uuidv4());
        }
      });
      
      const newComponent: ResumeComponent = {
        id: uuidv4(),
        componentName: template.componentName,
         moduleType: template.moduleType, // 【新增】
        title: template.title,
        props: propsCopy,
        styles: templates.find(t => t.id === this.selectedTemplateId)?.getStylesFor(template.componentName) || {},
      };
      this.resumeJson.push(newComponent);
    },

    deleteComponent(componentId: string) {
      const index = this.resumeJson.findIndex(c => c.id === componentId);
      if (index > -1) this.resumeJson.splice(index, 1);
    },
  },
});