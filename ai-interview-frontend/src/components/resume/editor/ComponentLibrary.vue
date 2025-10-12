<!-- src/components/resume/editor/ComponentLibrary.vue -->
<template>
  <div class="component-library">
    <h3 class="panel-title">组件库</h3>
    <p class="panel-desc">拖拽下方模块到画布中</p>
    <draggable
      :list="componentTemplates"
      :group="{ name: 'resume-components', pull: 'clone', put: false }"
      :sort="false"
      :clone="cloneComponent"
      item-key="componentName"
      class="template-list"
    >
      <template #item="{ element }">
        <div class="template-item">
          <!-- 【修复】直接使用 element.icon 作为组件，无需额外导入 -->
          <el-icon><component :is="element.icon" /></el-icon>
          <span>{{ element.title }}</span>
        </div>
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import draggable from 'vuedraggable';
import { v4 as uuidv4 } from 'uuid';
import type { ResumeComponent } from '@/store/modules/resumeEditor';
// 【修复】将图标导入移到这里，因为它们在模板数据中被引用
import { User, Briefcase, School, Trophy, CollectionTag, DocumentCopy } from '@element-plus/icons-vue';

// 定义可用的组件模板
const componentTemplates = ref([
  {
    componentName: 'BaseInfoModule',
    title: '基本信息',
    icon: User,
    props: {
      name: '你的姓名',
      photo: '',
      items: [
        { id: uuidv4(), icon: 'Phone', label: '电话', value: '138-0000-0000' },
        { id: uuidv4(), icon: 'Message', label: '邮箱', value: 'your-email@example.com' },
        { id: uuidv4(), icon: 'Postcard', label: '求职意向', value: '前端开发工程师' },
        { id: uuidv4(), icon: 'Location', label: '所在城市', value: '北京' },
      ],
    },
    styles: {
      padding: '20px 30px',
      borderBottom: '1px solid #f0f0f0',
    },
  },
  {
    componentName: 'SummaryModule',
    title: '个人总结',
    icon: DocumentCopy,
    props: {
      title: '个人总结',
      summary: '在这里简要介绍您的核心优势、技术热情和职业目标...'
    },
    styles: {
      padding: '20px 30px',
      borderBottom: '1px solid #f0f0f0',
    },
  },
  {
    componentName: 'EducationModule',
    title: '教育背景',
    icon: School,
    props: {
      title: '教育背景',
      educations: [
        {
          id: uuidv4(),
          school: '某某大学',
          major: '计算机科学与技术',
          degree: '学士',
          dateRange: '2018.09 - 2022.06',
          description: '主修课程：数据结构、算法、计算机网络等。'
        },
      ],
    },
    styles: {
      padding: '20px 30px',
      borderBottom: '1px solid #f0f0f0',
    },
  },
  {
    componentName: 'WorkExpModule',
    title: '工作经历',
    icon: Briefcase,
    props: {
      title: '工作经历',
      experiences: [
        {
          id: uuidv4(),
          company: 'A 公司',
          position: '前端开发工程师',
          dateRange: '2022.07 - 至今',
          description: '1. 负责 XX 业务线的 Web 前端开发工作。\n2. 使用 Vue 3 和 TypeScript 对现有项目进行重构，提升了 30% 的页面加载速度。\n3. 封装了多个可复用的业务组件，提高了团队的开发效率。',
        },
      ],
    },
    styles: {
      padding: '20px 30px',
      borderBottom: '1px solid #f0f0f0',
    },
  },
  {
    componentName: 'ProjectModule',
    title: '项目经历',
    icon: Trophy,
    props: {
      title: '项目经历',
      projects: [
        {
          id: uuidv4(),
          name: 'AI 模拟面试平台',
          role: '核心开发者',
          dateRange: '2023.01 - 至今',
          description: '项目描述...',
          techStack: 'Vue 3, TypeScript, Django',
          projectUrl: 'http://example.com'
        }
      ]
    },
    styles: {
      padding: '20px 30px',
      borderBottom: '1px solid #f0f0f0',
    },
  },
  {
    componentName: 'SkillsModule',
    title: '专业技能',
    icon: CollectionTag,
    props: {
      title: '专业技能',
      skills: [
        { id: uuidv4(), name: 'JavaScript / TypeScript', proficiency: '精通' },
        { id: uuidv4(), name: 'Vue.js / React.js', proficiency: '熟练' },
        { id: uuidv4(), name: 'Node.js', proficiency: '熟悉' },
      ],
    },
    styles: {
      padding: '20px 30px',
    },
  },
]);

const cloneComponent = (original: any): ResumeComponent => {
  const propsCopy = JSON.parse(JSON.stringify(original.props));
  
  ['items', 'educations', 'experiences', 'projects', 'skills'].forEach(key => {
      if (propsCopy[key] && Array.isArray(propsCopy[key])) {
          propsCopy[key].forEach((item: any) => item.id = uuidv4());
      }
  });

  return {
    ...original,
    id: uuidv4(),
    props: propsCopy,
  };
};
</script>

<style scoped>
/* 样式与之前保持一致，无需修改 */
.panel-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.panel-desc { font-size: 12px; color: #999; margin-bottom: 16px; }
.template-list { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.template-item { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 16px 8px; border: 1px solid #e8e8e8; border-radius: 4px; cursor: grab; background-color: #fafafa; transition: all 0.2s; }
.template-item:hover { border-color: #409eff; color: #409eff; box-shadow: 0 2px 8px rgba(0,0,0,0.09); }
.template-item .el-icon { font-size: 24px; margin-bottom: 8px; }
</style>