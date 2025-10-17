// src/store/modules/resumeEditor.ts
import { defineStore } from 'pinia';
import { v4 as uuidv4 } from 'uuid';
import { updateResumeApi, type ResumeItem } from '@/api/modules/resume';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import { ElMessage } from 'element-plus';
import { templates } from '@/resume-templates';
import { allTemplates } from '@/resume-templates/template-definitions';

export interface ResumeComponent {
  id: string;
  componentName: string;
  moduleType: string;
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

  actions: {
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
      if (!this.resumeMeta?.id) {
        ElMessage.error("无法保存，简历ID不存在。");
        return;
      }
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
      // --- 【核心修复】将 t.componentName 修改为 t.moduleType ---
      const template = allTemplates.find(t => t.moduleType === moduleType);
      
      if (!template) {
        console.error(`addComponent: 未找到 moduleType 为 "${moduleType}" 的模板定义`);
        return;
      }

      const propsCopy = JSON.parse(JSON.stringify(template.props));
      Object.keys(propsCopy).forEach(key => {
        if (Array.isArray(propsCopy[key])) {
          (propsCopy[key] as any[]).forEach((item: any) => {
            if(item && typeof item === 'object') {
              item.id = uuidv4();
            }
          });
        }
      });
      
      const newComponent: ResumeComponent = {
        id: uuidv4(),
        componentName: template.componentName,
        moduleType: template.moduleType,
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