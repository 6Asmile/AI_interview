// src/store/modules/resumeEditor.ts
import { defineStore } from 'pinia';
import { v4 as uuidv4 } from 'uuid';
import { updateResumeApi, type ResumeItem } from '@/api/modules/resume';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import { ElMessage } from 'element-plus';
import { templates } from '@/resume-templates';
import { allTemplates } from '@/resume-templates/template-definitions';
import { toRaw } from 'vue';

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

interface FullResumeItem extends Omit<ResumeItem, 'content_json'> {
  content_json: ResumeLayout | any[] | null;
}

interface ResumeEditorState {
  resumeMeta: FullResumeItem | null;
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
    // 【核心修复】恢复 updateResumeJson action
    updateResumeJson(newJson: ResumeLayout) {
      this.resumeJson = newJson;
    },
   // --- 【核心修复#1】重写 fetchResume ---
    async fetchResume(resumeId: number) {
        this.isLoading = true;
        this.resetState();
        try {
            const response = await getStructuredResumeApi(resumeId);
            this.resumeMeta = response as FullResumeItem;
            this.selectedTemplateId = response.template_name || 'sidebar-darkblue';

            // 1. 加载布局
            if (response.content_json && typeof response.content_json === 'object' && 'sidebar' in response.content_json) {
                this.resumeJson = response.content_json as ResumeLayout;
            } else if (Array.isArray(response.content_json)) {
                // 对于旧数据，先按规则分配一次
                this.distributeLayout(response.content_json, this.selectedTemplateId);
            }

            // 2. 加载完布局后，只应用样式和标题风格，不再重新分配布局
            this.applyStylesAndTitle(this.selectedTemplateId);

        } catch (error) { console.error(error); ElMessage.error("加载简历数据失败"); } 
        finally { this.isLoading = false; }
    },

    // --- 【核心修复#2】重写 saveResume ---
    async saveResume() {
      if (!this.resumeMeta?.id) return;
      this.isSaving = true;
      try {
        const payload = {
          title: this.resumeMeta.title,
          // 使用 toRaw() 获取纯净的 JS 对象，避免响应式代理带来的问题
          content_json: toRaw(this.resumeJson), 
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

   /**
     * @param componentId - 要选中的组件ID
     * @param _source - 'canvas' | 'config'，指示点击来源于哪里
     */
    selectComponent(componentId: string | null, _source: 'canvas' | 'config' = 'config') {
      if (this.selectedComponentId === componentId) {
        // 如果重复点击同一个，则取消选中
        this.selectedComponentId = null;
        return;
      }
      this.selectedComponentId = componentId;
      
      // 在这里我们不直接执行滚动，而是通过事件总线或让组件监听 selectedComponentId 的变化来触发。
      // Pinia 的 state 变化本身就是响应式的，组件可以 watch 它。
    },
    // --- 【核心修复#3】将 applyTemplate 拆分为两个独立的函数 ---

    // 函数一：只负责应用样式和标题（不改变布局）
    applyStylesAndTitle(templateId: string) {
        const template = templates.find(t => t.id === templateId);
        if (!template) return;
        
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
    },
    
    // 函数二：只负责重新分配布局
    distributeLayout(components: ResumeComponent[], templateId: string) {
        const template = templates.find(t => t.id === templateId);
        if (!template) return;

        if (template.layout === 'sidebar') {
            const newSidebar: ResumeComponent[] = [];
            const newMain: ResumeComponent[] = [];
            components.forEach(comp => {
                if (['BaseInfo', 'Skills'].includes(comp.moduleType)) newSidebar.push(comp);
                else newMain.push(comp);
            });
            this.resumeJson = { sidebar: newSidebar, main: newMain };
        } else {
            this.resumeJson = { sidebar: [], main: components };
        }
    },

    // 现在的 applyTemplate 变得更智能
    applyTemplate(templateId: string) {
      const newTemplate = templates.find(t => t.id === templateId);
      if (!newTemplate) return;

      const oldTemplate = templates.find(t => t.id === this.selectedTemplateId);
      this.selectedTemplateId = templateId;

      // 1. 总是应用新样式
      this.applyStylesAndTitle(templateId);

      // 2. 只有在布局类型发生变化时，才重新分配布局
      if (oldTemplate?.layout !== newTemplate.layout) {
          const allComponents = [...this.resumeJson.sidebar, ...this.resumeJson.main];
          this.distributeLayout(allComponents, templateId);
      }
    },

    addComponent(moduleType: string, zone: 'sidebar' | 'main' = 'main') {
        const template = allTemplates.find(t => t.moduleType === moduleType);
        if (!template) return;
        const propsCopy = JSON.parse(JSON.stringify(template.props));
        Object.keys(propsCopy).forEach(key => {
            if (Array.isArray(propsCopy[key])) (propsCopy[key] as any[]).forEach((item: any) => { if (item && typeof item === 'object') item.id = uuidv4(); });
        });
        const newComponent: ResumeComponent = {
            id: uuidv4(),
            componentName: template.componentName,
            moduleType: template.moduleType,
            title: template.title,
            props: propsCopy,
            styles: templates.find(t => t.id === this.selectedTemplateId)?.getStylesFor(template.componentName, template.moduleType) || {},
        };
        this.resumeJson[zone].push(newComponent);
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