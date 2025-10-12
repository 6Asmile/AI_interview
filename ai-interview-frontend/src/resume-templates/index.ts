// src/resume-templates/index.ts

// 定义一个模板的结构
export interface ResumeTemplate {
  name: string; // 模板名称，如 '简约蓝'
  id: string;   // 唯一ID，如 'simple-blue'
  getStylesFor: (componentName: string) => Record<string, any>; // 获取指定模块样式的函数
}

// --- 模板1：默认模板 (我们现在的样式) ---
const defaultTemplate: ResumeTemplate = {
  name: '经典默认',
  id: 'default',
  getStylesFor: (componentName) => {
    const baseStyles = { padding: '20px 30px' };
    if (componentName !== 'SkillsModule') {
      return { ...baseStyles, borderBottom: '1px solid #f0f0f0' };
    }
    return baseStyles;
  }
};

// --- 模板2：简约蓝模板 (示例) ---
const simpleBlueTemplate: ResumeTemplate = {
  name: '简约蓝',
  id: 'simple-blue',
  getStylesFor: (componentName) => {
    // 基础样式
    let styles: Record<string, any> = { padding: '15px 25px', color: '#333' };
    
    // 特定模块的样式覆盖
    if (componentName === 'BaseInfoModule') {
      styles.backgroundColor = '#f0f8ff';
    }
    if (componentName.includes('Module') && componentName !== 'BaseInfoModule') {
        styles.borderLeft = '3px solid #409eff';
        styles.marginBottom = '10px';
    }
    return styles;
  }
};

// 导出所有可用模板
export const templates: ResumeTemplate[] = [defaultTemplate, simpleBlueTemplate];