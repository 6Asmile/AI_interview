// src/store/modules/resumeEditor.ts
import { defineStore } from 'pinia';
import { v4 as uuidv4 } from 'uuid';
// 【修复#1】修正 API 函数的导入来源
import { updateResumeApi, type ResumeItem } from '@/api/modules/resume';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor'; // getStructuredResumeApi 在这里
import { ElMessage } from 'element-plus';
import { templates } from '@/resume-templates'; // 导入我们定义的模板

// 【修复#2】导出 ResumeComponent 类型，以便其他文件可以使用
export interface ResumeComponent {
  id: string;
  componentName: string;
  title: string;
  props: Record<string, any>;
  styles: Record<string, any>;
}

// 扩展 ResumeItem 类型以包含后端的新字段
// 注意：确保 api/modules/resume.ts 中的 ResumeItem 也已更新
interface FullResumeItem extends ResumeItem {
  template_name?: string;
}

// Store 的状态类型
interface ResumeEditorState {
  resumeMeta: FullResumeItem | null;
  resumeJson: ResumeComponent[];
  selectedComponentId: string | null;
  selectedTemplateId: string; // 当前选择的模板ID
  isLoading: boolean;
  isSaving: boolean;
}

export const useResumeEditorStore = defineStore('resumeEditor', {
  state: (): ResumeEditorState => ({
    resumeMeta: null,
    resumeJson: [],
    selectedComponentId: null,
    selectedTemplateId: 'default', // 默认模板ID
    isLoading: false,
    isSaving: false,
  }),

  getters: {
    // 根据 ID 查找并返回当前选中的组件对象
    selectedComponent(state): ResumeComponent | undefined {
      if (!state.selectedComponentId) return undefined;
      return state.resumeJson.find(c => c.id === state.selectedComponentId);
    },
  },

  actions: {
    // --- 核心API交互 ---

    async fetchResume(resumeId: number) {
      this.isLoading = true;
      this.resetState();
      try {
        const response = await getStructuredResumeApi(resumeId);
        this.resumeMeta = response;
        this.resumeJson = Array.isArray(response.content_json) ? response.content_json : [];
        // 从后端加载当前简历使用的模板
        this.selectedTemplateId = response.template_name || 'default';
      } catch (error) {
        console.error("获取简历详情失败", error);
        ElMessage.error("加载简历数据失败，请重试。");
      } finally {
        this.isLoading = false;
      }
    },

    async saveResume() {
      if (!this.resumeMeta?.id) {
        ElMessage.error("无法保存，简历ID不存在。");
        return;
      }
      this.isSaving = true;
      try {
        // 打包要发送到后端的数据
        const payload: Partial<FullResumeItem> = {
          title: this.resumeMeta.title,
          content_json: this.resumeJson,
          template_name: this.selectedTemplateId, // 保存当前选择的模板ID
        };
        const response = await updateResumeApi(this.resumeMeta.id, payload);

        // 用服务器返回的最新数据更新状态
        this.resumeMeta = response;
        this.resumeJson = response.content_json || [];
        this.selectedTemplateId = response.template_name || 'default';
        ElMessage.success('简历已成功保存！');
      } catch (error) {
        console.error("保存简历失败", error);
        ElMessage.error("保存失败，请检查网络后重试。");
      } finally {
        this.isSaving = false;
      }
    },
    
    resetState() {
      this.resumeMeta = null;
      this.resumeJson = [];
      this.selectedComponentId = null;
      this.selectedTemplateId = 'default';
      this.isLoading = false;
      this.isSaving = false;
    },

    // --- 编辑器交互 ---

    applyTemplate(templateId: string) {
      const template = templates.find(t => t.id === templateId);
      if (!template) {
        console.warn(`未找到ID为 "${templateId}" 的模板`);
        return;
      }

      this.selectedTemplateId = templateId;
      
      // 遍历画布上的所有组件，应用新模板的样式
      this.resumeJson.forEach(component => {
        component.styles = template.getStylesFor(component.componentName);
      });
      ElMessage.success(`已应用模板: ${template.name}`);
    },

    addComponent(component: Omit<ResumeComponent, 'id'>) {
      const newComponent: ResumeComponent = {
        ...component,
        id: uuidv4(),
      };
      this.resumeJson.push(newComponent);
      this.selectComponent(newComponent.id);
    },

    selectComponent(componentId: string | null) {
      this.selectedComponentId = componentId;
    },
    
    updateSelectedComponentProps(newProps: Record<string, any>) {
      if (this.selectedComponent) {
        this.selectedComponent.props = newProps;
      }
    },

    updateSelectedComponentStyles(newStyles: Record<string, any>) {
        if (this.selectedComponent) {
            this.selectedComponent.styles = newStyles;
        }
    },

    deleteComponent(componentId: string) {
      const index = this.resumeJson.findIndex(c => c.id === componentId);
      if (index > -1) {
        this.resumeJson.splice(index, 1);
        if (this.selectedComponentId === componentId) {
          this.selectedComponentId = null;
        }
      }
    },

    moveComponent({ oldIndex, newIndex }: { oldIndex: number, newIndex: number }) {
      const [movedItem] = this.resumeJson.splice(oldIndex, 1);
      this.resumeJson.splice(newIndex, 0, movedItem);
    }
  },
});