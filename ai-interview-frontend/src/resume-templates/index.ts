// src/resume-templates/index.ts

export interface ResumeTemplate {
  name: string;
  id: string;
  layout: 'single-column' | 'sidebar';
  pageStyles?: Record<string, any>;
  // 【核心修复】统一函数签名，接收两个参数
  getStylesFor: (componentName: string, moduleType: string) => Record<string, any>;
}

// --- 模板1：经典默认 (修复版) ---
const defaultTemplate: ResumeTemplate = {
  name: '经典默认',
  id: 'default',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff' },
  // 【核心修复】函数接收两个参数，即使只用到了 componentName
  getStylesFor: (componentName, _moduleType) => {
    const baseStyles = { padding: '20px 30px' };
    if (!['SkillsModule', 'CustomModule'].includes(componentName)) {
      return { ...baseStyles, borderBottom: '1px solid #f0f0f0' };
    }
    return baseStyles;
  }
};

// --- 模板2：专业深蓝 (修复版) ---
const professionalDarkBlueTemplate: ResumeTemplate = {
  name: '专业深蓝',
  id: 'professional-darkblue',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', color: '#3d3d3d', fontFamily: '微软雅黑, sans-serif', fontWeight: 400 },
  // 【核心修复】函数接收两个参数
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      return { padding: '25px 40px', display: 'flex', alignItems: 'flex-end', borderBottom: '1px solid #f0f0f0', marginBottom: '10px' };
    }
    return { padding: '15px 40px 20px' };
  }
};

// --- 模板3：简约线条 (修复版) ---
const modernAccentTemplate: ResumeTemplate = {
  name: '简约线条',
  id: 'modern-accent',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', fontFamily: '微软雅黑, sans-serif', fontWeight: 400, color: 'rgb(117, 117, 117)' },
  // 【核心修复】函数接收两个参数
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      return { padding: '10px 30px 5px', color: 'rgb(18, 28, 38)', fontWeight: 400 };
    }
    return { padding: '10px 30px 20px', fontWeight: 500, color: 'rgb(117, 117, 117)' };
  }
};

// --- 模板4: 商务灰 (修复版) ---
const businessGrayTemplate: ResumeTemplate = {
  name: '商务灰',
  id: 'business-gray',
  layout: 'single-column',
  pageStyles: { backgroundColor: '#fff', fontFamily: '微软雅黑, sans-serif', fontWeight: 400, color: 'rgb(117, 117, 117)' },
  getStylesFor: (componentName, _moduleType) => {
    if (componentName === 'BaseInfoModule') {
      return { padding: '10px 30px 0px 25px', backgroundColor: 'rgb(128, 128, 128)', color: '#fff' };
    }
    return { padding: '0px 30px 20px 25px' };
  }
};

// --- 【核心修复】模板5：左右分栏-深蓝 (优化版) ---
const sidebarDarkBlueTemplate: ResumeTemplate = {
  name: '左右分栏-深蓝',
  id: 'sidebar-darkblue',
  layout: 'sidebar',
  pageStyles: {
    padding: '0',
    fontFamily: '微软雅黑, sans-serif',
  },
  getStylesFor: (_componentName, moduleType) => {
    // 左侧栏模块的样式
    if (['BaseInfo', 'Skills'].includes(moduleType)) { // 假设技能模块也放在侧边栏
      return {
        color: '#fff',
        padding: '0 10px',
        marginBottom: '40px',
      };
    }
    // 右侧主内容区模块的样式
    return {
      padding: '0 20px 25px', // 增加底部间距
      color: '#3d3d3d',
    };
  }
};

export const templates: ResumeTemplate[] = [
  defaultTemplate,
  professionalDarkBlueTemplate,
  modernAccentTemplate,
  businessGrayTemplate,
  sidebarDarkBlueTemplate,
];