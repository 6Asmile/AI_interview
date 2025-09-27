<template>
  <!-- 模板部分与之前相同，它现在依赖于 props.resumeData -->
  <div class="resume-preview-a4" v-if="resumeData">
    <!-- 个人信息 -->
    <header class="resume-header">
      <h1>{{ resumeData.full_name || '姓名' }}</h1>
      <p class="job-title">{{ resumeData.job_title || '期望职位' }}</p>
      <div class="contact-info">
        <span>{{ resumeData.city || '城市' }}</span>
        <span class="separator">|</span>
        <span>{{ resumeData.phone || '电话' }}</span>
        <span class="separator">|</span>
        <span>{{ resumeData.email || '邮箱' }}</span>
      </div>
    </header>

    <!-- 个人总结 -->
    <section class="resume-section" v-if="resumeData.summary">
      <h2 class="section-title">个人总结</h2>
      <div class="section-content">
        <p>{{ resumeData.summary }}</p>
      </div>
    </section>

    <!-- 工作经历 -->
    <section class="resume-section" v-if="resumeData.work_experiences.length > 0">
      <h2 class="section-title">工作经历</h2>
      <div class="section-content">
        <div v-for="(exp, index) in resumeData.work_experiences" :key="index" class="item">
          <div class="item-header">
            <h3 class="item-title">{{ exp.company || '公司名称' }}</h3>
            <span class="item-subtitle">{{ exp.position || '职位' }}</span>
            <span class="item-date">{{ formatDate(exp.start_date) }} - {{ formatDate(exp.end_date) || '至今' }}</span>
          </div>
          <p class="item-desc" style="white-space: pre-wrap;">{{ exp.description }}</p>
        </div>
      </div>
    </section>

    <!-- 项目经历 -->
    <section class="resume-section" v-if="resumeData.project_experiences.length > 0">
      <h2 class="section-title">项目经历</h2>
      <div class="section-content">
        <div v-for="(proj, index) in resumeData.project_experiences" :key="index" class="item">
          <div class="item-header">
            <h3 class="item-title">{{ proj.project_name || '项目名称' }}</h3>
            <span class="item-subtitle">{{ proj.role || '担任角色' }}</span>
            <span class="item-date">{{ formatDate(proj.start_date) }} - {{ formatDate(proj.end_date) || '至今' }}</span>
          </div>
          <p class="item-desc" style="white-space: pre-wrap;">{{ proj.description }}</p>
        </div>
      </div>
    </section>
    
    <!-- 教育背景 -->
    <section class="resume-section" v-if="resumeData.educations.length > 0">
      <h2 class="section-title">教育背景</h2>
      <div class="section-content">
        <div v-for="(edu, index) in resumeData.educations" :key="index" class="item">
          <div class="item-header">
            <h3 class="item-title">{{ edu.school || '学校名称' }}</h3>
            <span class="item-subtitle">{{ edu.degree || '学位' }} | {{ edu.major || '专业' }}</span>
            <span class="item-date">{{ formatDate(edu.start_date) }} - {{ formatDate(edu.end_date) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 专业技能 -->
    <section class="resume-section" v-if="resumeData.skills.length > 0">
      <h2 class="section-title">专业技能</h2>
      <div class="section-content skills-list">
        <span v-for="(skill, index) in resumeData.skills" :key="index" class="skill-tag">
          {{ skill.skill_name }}
          <span v-if="skill.proficiency" class="proficiency">({{ skill.proficiency }})</span>
        </span>
      </div>
    </section>

  </div>
</template>

<script setup lang="ts">
// 【核心修正】移除所有未使用的导入
// import { computed } from 'vue'; // 未使用
// import { useResumeEditorStore } from '@/store/modules/resumeEditor'; // 未使用
import type { StructuredResume } from '@/api/modules/resume';

// 【核心修正】只保留 props 定义，因为该组件现在只接收数据
const props = defineProps<{
  resumeData: StructuredResume | null;
}>();

// 【核心修正】为 formatDate 函数提供完整的实现，确保它总能返回一个字符串
const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) {
    return ''; // 如果日期为空，返回空字符串
  }
  try {
    const d = new Date(dateString);
    // 检查日期是否有效，防止 "Invalid Date"
    if (isNaN(d.getTime())) {
      return '';
    }
    // 返回格式化的年月
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}`;
  } catch (e) {
    // 如果解析出错，也返回空字符串
    return '';
  }
};
</script>

<style scoped>
/* 样式保持不变 */
.resume-preview-a4 {
  width: 210mm;
  min-height: 297mm;
  padding: 25mm;
  background: white;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  color: #333;
  line-height: 1.6;
}

.resume-header {
  text-align: center;
  border-bottom: 2px solid #333;
  padding-bottom: 15px;
  margin-bottom: 20px;
}

.resume-header h1 {
  font-size: 28px;
  margin: 0 0 5px 0;
  font-weight: 600;
}

.resume-header .job-title {
  font-size: 20px;
  color: #555;
  margin: 0 0 10px 0;
}

.contact-info {
  font-size: 14px;
  color: #666;
}
.contact-info .separator {
  margin: 0 10px;
}

.resume-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid #ccc;
  padding-bottom: 8px;
  margin-bottom: 15px;
}

.item {
  margin-bottom: 15px;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  margin-bottom: 5px;
}

.item-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  margin-right: 10px;
}

.item-subtitle {
  color: #555;
  flex-grow: 1;
}

.item-date {
  font-size: 14px;
  color: #777;
  flex-shrink: 0;
}

.item-desc {
  margin: 0;
  color: #444;
}

.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.skill-tag {
  background-color: #f0f2f5;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 14px;
}
.proficiency {
  color: #909399;
  margin-left: 5px;
}
</style>