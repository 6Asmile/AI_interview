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
  // 【核心修复#1】恢复 selectedComponentId 状态
  selectedComponentId: string | null;
  selectedTemplateId: string;
  isLoading: boolean;
  isSaving: boolean;
}

export const useResumeEditorStore = defineStore('resumeEditor', {
  state: (): ResumeEditorState => ({
    resumeMeta: null,
    resumeJson: [],
    // 【核心修复#1】恢复 selectedComponentId 状态
    selectedComponentId: null,
    selectedTemplateId: 'professional-darkblue',
    isLoading: false,
    isSaving: false,
  }),

  // 【核心修复#1】恢复 selectedComponent getter
  getters: {
    selectedComponent(state): ResumeComponent | undefined {
      if (!state.selectedComponentId) return undefined;
      return state.resumeJson.find(c => c.id === state.selectedComponentId);
    },
  },

  actions: {
    // ... fetchResume, saveResume, resetState 保持不变 ...
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
        this.selectedComponentId = null;
        this.selectedTemplateId = 'professional-darkblue';
    },

      applyTemplate(templateId: string) {
      const template = templates.find(t => t.id === templateId);
      if (!template) return;

      this.selectedTemplateId = templateId;
      
      this.resumeJson.forEach(component => {
        component.styles = template.getStylesFor(component.componentName, component.moduleType);

        if (component.componentName !== 'BaseInfoModule') {
          if (templateId === 'modern-accent') component.props.titleStyle = 'style2';
          else if (templateId === 'business-gray') component.props.titleStyle = 'style3';
          else if (templateId === 'sidebar-darkblue') component.props.titleStyle = 'style4';
          else component.props.titleStyle = 'style1';
        }
        
        // --- 【核心修改】为分栏模板设置默认分区 ---
        if (template.layout === 'sidebar') {
            // 如果模块还没有分区信息，就给它一个默认值
            if (!component.props.layoutZone) {
                if (['BaseInfo', 'Skills'].includes(component.moduleType)) {
                    component.props.layoutZone = 'sidebar';
                } else {
                    component.props.layoutZone = 'main';
                }
            }
        } else {
            // 如果切换回单栏布局，清除所有分区信息
            delete component.props.layoutZone;
        }
      });
    },

    updateResumeJson(newJson: ResumeComponent[]) {
      this.resumeJson = newJson;
    },

    // 【核心修复#1】恢复 selectComponent action
    selectComponent(componentId: string | null) {
      this.selectedComponentId = componentId;
    },

    addComponent(moduleType: string) {
      const template = allTemplates.find(t => t.moduleType === moduleType);
      if (!template) return;
      const propsCopy = JSON.parse(JSON.stringify(template.props));
      Object.keys(propsCopy).forEach(key => {
        if (Array.isArray(propsCopy[key])) {
          (propsCopy[key] as any[]).forEach((item: any) => { if (item && typeof item === 'object') item.id = uuidv4(); });
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
      this.resumeJson.push(newComponent);
    },

    deleteComponent(componentId: string) {
      const index = this.resumeJson.findIndex(c => c.id === componentId);
      if (index > -1) {
        this.resumeJson.splice(index, 1);
        // 如果删除的是当前选中的组件，则取消选中
        if (this.selectedComponentId === componentId) {
            this.selectedComponentId = null;
        }
      }
    },
     // 【核心新增】用于跨区域拖拽更新
    updateLayoutZones(sidebarModules: ResumeComponent[], mainModules: ResumeComponent[]) {
        sidebarModules.forEach(m => m.props.layoutZone = 'sidebar');
        mainModules.forEach(m => m.props.layoutZone = 'main');
        this.resumeJson = [...sidebarModules, ...mainModules];
    },

  },
});