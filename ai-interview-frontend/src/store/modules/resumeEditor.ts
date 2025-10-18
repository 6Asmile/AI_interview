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

export interface ResumeLayout {
  sidebar: ResumeComponent[];
  main: ResumeComponent[];
}

// // 修正 FullResumeItem，使其与 ResumeItem 的 content_json 类型兼容
// interface FullResumeItem extends Omit<ResumeItem, 'content_json'> {
//   content_json: ResumeLayout | any[] | null; // 允许两种类型
// }

interface ResumeEditorState {
   resumeMeta: ResumeItem | null; // 直接使用导入的 ResumeItem
  resumeJson: ResumeLayout;
  selectedComponentId: string | null;
  selectedTemplateId: string;
  isLoading: boolean;
  isSaving: boolean;
}

export const useResumeEditorStore = defineStore('resumeEditor', {
  state: (): ResumeEditorState => ({
    resumeMeta: null,
    resumeJson: { sidebar: [], main: [] },
    selectedComponentId: null,
    selectedTemplateId: 'sidebar-darkblue',
    isLoading: false,
    isSaving: false,
  }),
  
  getters: {
    selectedComponent(state): ResumeComponent | undefined {
        if (!state.selectedComponentId) return undefined;
        return [...state.resumeJson.sidebar, ...state.resumeJson.main].find(c => c.id === state.selectedComponentId);
    }
  },

  actions: {
    async fetchResume(resumeId: number) {
      this.isLoading = true;
      this.resetState();
      try {
        const response = await getStructuredResumeApi(resumeId);
        this.resumeMeta = response as ResumeItem; // 类型断言
        if (response.content_json && 'sidebar' in response.content_json && 'main' in response.content_json) {
            this.resumeJson = response.content_json as ResumeLayout; // 类型断言
        } else if (Array.isArray(response.content_json)) {
            this.resumeJson = { sidebar: [], main: response.content_json };
        }
        this.selectedTemplateId = response.template_name || 'sidebar-darkblue';
      } catch (error) { console.error(error); ElMessage.error("加载简历数据失败"); } 
      finally { this.isLoading = false; }
    },
    async saveResume() {
      if (!this.resumeMeta?.id) return;
      this.isSaving = true;
      try {
        const payload = {
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
      this.resumeJson = { sidebar: [], main: [] };
      this.selectedComponentId = null;
      this.selectedTemplateId = 'sidebar-darkblue';
    },
    selectComponent(componentId: string | null) {
      this.selectedComponentId = componentId;
    },
    applyTemplate(templateId: string) {
        const template = templates.find(t => t.id === templateId);
        if (!template) return;
        this.selectedTemplateId = templateId;
        const allComponents = [...this.resumeJson.sidebar, ...this.resumeJson.main];
        allComponents.forEach(component => {
            component.styles = template.getStylesFor(component.componentName, component.moduleType);
            if (component.componentName !== 'BaseInfoModule') {
                if (templateId === 'modern-accent') component.props.titleStyle = 'style2';
                else if (templateId === 'business-gray') component.props.titleStyle = 'style3';
                else if (templateId === 'sidebar-darkblue') component.props.titleStyle = 'style4';
                else component.props.titleStyle = 'style1';
            }
        });
        if (template.layout === 'sidebar') {
            const newMain: ResumeComponent[] = [];
            const newSidebar: ResumeComponent[] = [];
            allComponents.forEach(comp => {
                if (['BaseInfo', 'Skills'].includes(comp.moduleType)) newSidebar.push(comp);
                else newMain.push(comp);
            });
            this.resumeJson = { sidebar: newSidebar, main: newMain };
        } else {
            this.resumeJson = { sidebar: [], main: allComponents };
        }
    },
     // 【核心升级】addComponent 接收一个可选的 'zone' 参数
    addComponent(moduleType: string, zone: 'sidebar' | 'main' = 'main') {
      const template = allTemplates.find(t => t.moduleType === moduleType);
      if (!template) {
        console.error(`addComponent: 未找到 moduleType 为 "${moduleType}" 的模板定义`);
        return;
      }

      const propsCopy = JSON.parse(JSON.stringify(template.props));
      Object.keys(propsCopy).forEach(key => {
        if (Array.isArray(propsCopy[key])) {
          (propsCopy[key] as any[]).forEach((item: any) => {
            if(item && typeof item === 'object') item.id = uuidv4();
          });
        }
      });
      
      const newComponent: ResumeComponent = {
        id: uuidv4(),
        componentName: template.componentName,
        moduleType: template.moduleType,
        title: template.title,
        props: propsCopy,
        styles: templates.find(t => t.id === this.selectedTemplateId)?.getStylesFor(template.componentName, template.moduleType) || {},
      };
      
      // 根据 zone 参数决定将模块添加到哪个数组
      if (zone === 'sidebar') {
          this.resumeJson.sidebar.push(newComponent);
      } else {
          this.resumeJson.main.push(newComponent);
      }
    },
    deleteComponent(componentId: string) {
        let index = this.resumeJson.sidebar.findIndex(c => c.id === componentId);
        if (index > -1) {
            this.resumeJson.sidebar.splice(index, 1);
            if (this.selectedComponentId === componentId) this.selectedComponentId = null;
            return;
        }
        index = this.resumeJson.main.findIndex(c => c.id === componentId);
        if (index > -1) {
            this.resumeJson.main.splice(index, 1);
            if (this.selectedComponentId === componentId) this.selectedComponentId = null;
        }
    },
  },
});