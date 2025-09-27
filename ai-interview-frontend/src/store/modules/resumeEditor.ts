// src/store/modules/resumeEditor.ts
import { defineStore } from 'pinia';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import { updateResumeApi } from '@/api/modules/resume';
import type { StructuredResume, EducationItem, WorkExperienceItem, ProjectExperienceItem, SkillItem } from '@/api/modules/resume';
import { ElMessage } from 'element-plus';

// 定义一个空的简历结构，用于清空或初始化
const getInitialState = (): StructuredResume => ({
  id: 0,
  user: 0,
  title: '我的在线简历',
  file: null,
  file_type: '',
  file_size: 0,
  is_default: false,
  status: 'draft',
  created_at: '',
  updated_at: '',
  parsed_content: '',
  full_name: '',
  phone: '',
  email: '',
  job_title: '',
  city: '',
  summary: '',
  educations: [],
  work_experiences: [],
  project_experiences: [], // 新增
  skills: [], // 新增
});


export const useResumeEditorStore = defineStore('resumeEditor', {
  state: () => ({
    resumeData: getInitialState() as StructuredResume,
    isLoading: false,
    isSaving: false,
    selectedTemplate: 'TemplateA' as string, // 【新增】当前选择的模板
  }),

  actions: {
    // 1. 从服务器获取完整的结构化简历数据
    async fetchResume(resumeId: number) {
      this.isLoading = true;
      try {
        const response = await getStructuredResumeApi(resumeId);
        this.resumeData = response;
        ElMessage.success('简历数据加载成功！');
      } catch (error) {
        console.error("获取简历详情失败", error);
        ElMessage.error("加载简历数据失败，请重试。");
      } finally {
        this.isLoading = false;
      }
    },

    // 2. 保存整个简历数据到服务器
    async saveResume() {
      if (!this.resumeData.id) return;
      this.isSaving = true;
      try {
        const response = await updateResumeApi(this.resumeData.id, this.resumeData);
        this.resumeData = response;
        ElMessage.success('简历已成功保存！');
      } catch (error) {
        console.error("保存简历失败", error);
        ElMessage.error("保存失败，请检查网络后重试。");
      } finally {
        this.isSaving = false;
      }
    },
    
    // 【新增】设置模板
    setTemplate(templateName: string) {
      this.selectedTemplate = templateName;
    },

    // 3. 重置状态
    resetState() {
      this.resumeData = getInitialState();
      this.selectedTemplate = 'TemplateA';
    },

    // --- 以下是操作各个子模块的方法 ---

    // 教育经历
    addEducation() {
      this.resumeData.educations.push({
        school: '', degree: '', major: '', start_date: '', end_date: ''
      } as EducationItem);
    },
    removeEducation(index: number) {
      this.resumeData.educations.splice(index, 1);
    },

    // 工作经历
    addWorkExperience() {
      this.resumeData.work_experiences.push({
        company: '', position: '', start_date: '', end_date: null, description: ''
      } as WorkExperienceItem);
    },
    removeWorkExperience(index: number) {
      this.resumeData.work_experiences.splice(index, 1);
    },

    // 【新增】项目经历
    addProjectExperience() {
      this.resumeData.project_experiences.push({
        project_name: '', role: '', start_date: '', end_date: null, description: ''
      } as ProjectExperienceItem);
    },
    removeProjectExperience(index: number) {
      this.resumeData.project_experiences.splice(index, 1);
    },

    // 【新增】专业技能
    addSkill() {
      this.resumeData.skills.push({
        skill_name: '', proficiency: ''
      } as SkillItem);
    },
    removeSkill(index: number) {
      this.resumeData.skills.splice(index, 1);
    }
  },
});