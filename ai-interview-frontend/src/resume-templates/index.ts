// src/resume-templates/index.ts

export interface ResumeTemplate {
  name: string; // 模板名称
  id: string;   // 唯一ID
  // 新增一个全局页面样式
  pageStyles?: Record<string, any>;
  getStylesFor: (componentName: string) => Record<string, any>;
}

// --- 模板1：经典默认 (保持不变，作为备用) ---
const defaultTemplate: ResumeTemplate = {
  name: '经典默认',
  id: 'default',
  pageStyles: {
    backgroundColor: '#fff',
  },
  getStylesFor: (componentName) => {
    const baseStyles = { padding: '20px 30px' };
    if (componentName !== 'SkillsModule' && componentName !== 'CustomModule') {
      return { ...baseStyles, borderBottom: '1px solid #f0f0f0' };
    }
    return baseStyles;
  }
};

// --- 模板2：专业深蓝 (复刻您提供的模板) ---
const professionalDarkBlueTemplate: ResumeTemplate = {
  name: '专业深蓝',
  id: 'professional-darkblue',
  // 全局页面样式
  pageStyles: {
    backgroundColor: '#fff',
    color: '#757575',
    fontFamily: '微软雅黑, sans-serif',
    fontWeight: 500,
  },
  // 各模块的独立样式
  getStylesFor: (componentName) => {
    switch (componentName) {
      case 'BaseInfoModule':
        return {
          padding: '25px 40px',
          display: 'flex',
          alignItems: 'flex-end',
          borderBottom: '10px solid #f3f3f3', // 用边框模拟模块间距
        };
      
      // 所有内容模块使用统一的样式
      case 'SummaryModule':
      case 'EducationModule':
      case 'WorkExpModule':
      case 'ProjectModule':
      case 'SkillsModule':
      case 'GenericListModule':
      case 'CustomModule':
        return {
          padding: '0px 40px 20px',
          marginBottom: '10px'
        };

      default:
        return {};
    }
  }
};

export const templates: ResumeTemplate[] = [
  defaultTemplate,
  professionalDarkBlueTemplate,
];