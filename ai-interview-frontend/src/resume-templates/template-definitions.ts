// src/resume-templates/template-definitions.ts
import { v4 as uuidv4 } from 'uuid';
import {
  User, School, Briefcase, Trophy, CollectionTag, 
  DocumentCopy, Star, Files, Postcard, Reading, Bell, Edit
} from '@element-plus/icons-vue';

export interface ModuleTemplate {
  componentName: string;
  moduleType: string;
  title: string;
  icon: any;
  props: Record<string, any>;
}

export const allTemplates: ModuleTemplate[] = [
  { componentName: 'BaseInfoModule', moduleType: 'BaseInfo', title: '基本信息', icon: User, props: { show: true, name: '你的姓名', photo: '', items: [{ id: uuidv4(), icon: 'Phone', label: '电话', value: '138-0000-0000' }, { id: uuidv4(), icon: 'Message', label: '邮箱', value: 'your-email@example.com' }] } },
  { componentName: 'SummaryModule', moduleType: 'Summary', title: '自我评价', icon: DocumentCopy, props: { show: true, title: '自我评价', summary: '在这里简要介绍您的核心优势...' } },
  { componentName: 'EducationModule', moduleType: 'Education', title: '教育背景', icon: School, props: { show: true, title: '教育背景', educations: [{ id: uuidv4(), school: '某某大学', major: '计算机科学与技术', degree: '学士', dateRange: ['2018-09', '2022-06'], description: '' }] } },
  { componentName: 'WorkExpModule', moduleType: 'WorkExp', title: '工作/实习经历', icon: Briefcase, props: { show: true, title: '工作/实习经历', experiences: [{ id: uuidv4(), company: 'A 公司', position: '前端开发工程师', dateRange: ['2022-07', null], description: '1. ...' }] } },
  { componentName: 'ProjectModule', moduleType: 'Project', title: '项目经历', icon: Trophy, props: { show: true, title: '项目经历', projects: [{ id: uuidv4(), name: 'AI 模拟面试平台', role: '核心开发者', dateRange: ['2023-01', null], description: '项目描述...', techStack: 'Vue 3, TypeScript, Django' }] } },
  { componentName: 'SkillsModule', moduleType: 'Skills', title: '专业技能', icon: CollectionTag, props: { show: true, title: '专业技能', skills: [{ id: uuidv4(), name: 'JavaScript / TypeScript', proficiency: '精通' }] } },
  { componentName: 'GenericListModule', moduleType: 'CampusExp', title: '在校经历', icon: Star, props: { show: true, title: '在校经历', items: [{ id: uuidv4(), title: '担任学生会主席', subtitle: '2020.09 - 2021.06', description: '组织了校园歌手大赛等活动...' }] } },
  { componentName: 'GenericListModule', moduleType: 'Certificates', title: '资格证书', icon: Files, props: { show: true, title: '资格证书', items: [{ id: uuidv4(), title: '大学英语六级 (CET-6)', subtitle: '580分', description: '' }] } },
  { componentName: 'GenericListModule', moduleType: 'Contests', title: '竞赛经历', icon: Postcard, props: { show: true, title: '竞赛经历', items: [{ id: uuidv4(), title: '蓝桥杯大赛', subtitle: '国家级一等奖', description: '参赛项目...' }] } },
  { componentName: 'GenericListModule', moduleType: 'Awards', title: '获奖情况', icon: Bell, props: { show: true, title: '获奖情况', items: [{ id: uuidv4(), title: '国家奖学金', subtitle: '2021', description: '' }] } },
  { componentName: 'GenericListModule', moduleType: 'Publications', title: '论文/期刊', icon: Reading, props: { show: true, title: '论文/期刊', items: [{ id: uuidv4(), title: '《关于XXX的研究》', subtitle: '发表于《计算机学报》', description: '本人为第一作者...' }] } },
  { componentName: 'CustomModule', moduleType: 'Custom', title: '自定义模块', icon: Edit, props: { show: true, title: '自定义标题', content: '在这里填写您的自定义内容...' } },
];