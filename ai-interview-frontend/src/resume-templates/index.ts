// src/resume-templates/index.ts

export interface ResumeTemplate {
  name: string;
  id: string;
  layout: 'single-column' | 'sidebar';
  pageStyles?: Record<string, any>;
  getStylesFor: (componentName: string, moduleType: string) => Record<string, any>;
}

// --- 模板1：经典默认 (优化版) ---
const defaultTemplate: ResumeTemplate = {
  name: '经典默认',
  id: 'default',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff' },
  // 【核心优化】不再处理 borderBottom 或 marginBottom
  getStylesFor: (_componentName, _moduleType) => {
    return { 
      padding: '20px 30px', 
    };
  }
};

// --- 模板2：专业深蓝 (优化版) ---
const professionalDarkBlueTemplate: ResumeTemplate = {
  name: '专业深蓝',
  id: 'professional-darkblue',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', color: '#3d3d3d', fontFamily: '微软雅黑, sans-serif', fontWeight: 400 },
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      // 【核心优化】移除 marginBottom
      return { padding: '25px 40px', display: 'flex', alignItems: 'flex-end' };
    }
    // 【核心优化】移除 marginBottom
    return { padding: '15px 40px 20px' };
  }
};

// --- 模板3：简约线条 (优化版) ---
const modernAccentTemplate: ResumeTemplate = {
  name: '简约线条',
  id: 'modern-accent',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', fontFamily: '微软雅黑, sans-serif', fontWeight: 400, color: 'rgb(117, 117, 117)' },
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      return { padding: '10px 30px 5px', color: 'rgb(18, 28, 38)', fontWeight: 400 };
    }
    // 【核心优化】移除 marginBottom
    return { padding: '10px 30px 20px', fontWeight: 500, color: 'rgb(117, 117, 117)' };
  }
};

// --- 模板4: 商务灰 (优化版) ---
const businessGrayTemplate: ResumeTemplate = {
  name: '商务灰',
  id: 'business-gray',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', fontFamily: '微软雅黑, sans-serif', fontWeight: 400, color: 'rgb(117, 117, 117)' },
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      return { padding: '10px 30px 0px 25px', backgroundColor: 'rgb(128, 128, 128)', color: '#fff' };
    }
    // 【核心优化】移除 marginBottom
    return { padding: '0px 30px 20px 25px' };
  }
};

// --- 模板5：左右分栏-深蓝 (保持不变) ---
const sidebarDarkBlueTemplate: ResumeTemplate = {
  name: '左右分栏-深蓝',
  id: 'sidebar-darkblue',
  layout: 'sidebar',
  pageStyles: { padding: '0', fontFamily: '微软雅黑, sans-serif' },
  getStylesFor: (_componentName, moduleType) => {
    if (['BaseInfo', 'Skills'].includes(moduleType)) {
      return { color: '#fff', padding: '0 20px', marginBottom: '45px' };
    }
    return { padding: '0 20px 20px', color: 'rgb(53, 53, 53)' };
  }
};

export const templates: ResumeTemplate[] = [
  defaultTemplate,
  professionalDarkBlueTemplate,
  modernAccentTemplate,
  businessGrayTemplate,
  sidebarDarkBlueTemplate,
];