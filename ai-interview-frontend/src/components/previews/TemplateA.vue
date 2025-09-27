<template>
  <div class="resume-preview a4-paper">
    <header class="resume-header">
      <h1>{{ resumeData.full_name || '姓名' }}</h1>
      <p>{{ resumeData.job_title || '期望职位' }}</p>
      <div class="contact-info">
        <span>{{ resumeData.city || '城市' }}</span>
        <span>{{ resumeData.phone || '电话' }}</span>
        <span>{{ resumeData.email || '邮箱' }}</span>
      </div>
    </header>

    <section class="resume-section" v-if="resumeData.summary">
      <h2 class="section-title">个人总结</h2>
      <p>{{ resumeData.summary }}</p>
    </section>

    <section class="resume-section" v-if="resumeData.educations?.length">
      <h2 class="section-title">教育背景</h2>
      <div v-for="edu in resumeData.educations" :key="edu.id" class="section-item">
        <div class="item-header">
          <h3>{{ edu.school || '学校名称' }}</h3>
          <span>{{ formatDate(edu.start_date) }} - {{ formatDate(edu.end_date) }}</span>
        </div>
        <p>{{ edu.degree || '学位' }} | {{ edu.major || '专业' }}</p>
      </div>
    </section>
    
    <section class="resume-section" v-if="resumeData.work_experiences?.length">
      <h2 class="section-title">工作经历</h2>
      <div v-for="exp in resumeData.work_experiences" :key="exp.id" class="section-item">
        <div class="item-header">
          <h3>{{ exp.company || '公司名称' }}</h3>
          <span>{{ formatDate(exp.start_date) }} - {{ formatDate(exp.end_date) || '至今' }}</span>
        </div>
        <h4>{{ exp.position || '职位' }}</h4>
        <p class="description-text">{{ exp.description }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
defineProps<{ resumeData: any }>();

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}`;
};
</script>

<style scoped>
.a4-paper {
  width: 210mm;
  min-height: 297mm;
  padding: 25mm;
  background: white;
  box-shadow: 0 0 10px rgba(0,0,0,0.1);
  box-sizing: border-box;
}
.resume-header { text-align: center; margin-bottom: 20px; }
h1 { margin: 0; font-size: 24px; }
.contact-info { display: flex; justify-content: center; gap: 15px; margin-top: 10px; color: #555; }
.resume-section { margin-top: 20px; }
.section-title { font-size: 18px; font-weight: bold; border-bottom: 2px solid #333; padding-bottom: 5px; margin-bottom: 10px; }
.section-item { margin-top: 10px; }
.item-header { display: flex; justify-content: space-between; align-items: baseline; }
h3, h4 { margin: 0; }
h3 { font-size: 16px; }
h4 { font-size: 14px; font-weight: normal; color: #555; margin-top: 5px; }
p { margin: 5px 0; line-height: 1.6; }
.description-text { white-space: pre-wrap; }
</style>