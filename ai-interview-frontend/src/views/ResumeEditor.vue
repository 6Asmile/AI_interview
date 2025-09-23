<template>
  <div class="page-container editor-container">
    <el-container v-if="!loading && resumeData" class="editor-layout">
      <!-- 左侧导航栏 -->
      <el-aside width="200px" class="editor-aside">
        <div class="resume-title-display">
          <h3>{{ resumeData.title }}</h3>
        </div>
        <el-menu :default-active="activeSection" @select="handleSectionSelect">
          <el-menu-item index="basic-info">
            <el-icon><User /></el-icon>
            <span>基本信息</span>
          </el-menu-item>
          <el-menu-item index="education">
             <el-icon><Reading /></el-icon>
            <span>教育背景</span>
          </el-menu-item>
          <el-menu-item index="work-experience">
            <el-icon><Briefcase /></el-icon>
            <span>工作经历</span>
          </el-menu-item>
          <!-- TODO: 添加更多模块导航 -->
        </el-menu>
        <div class="aside-footer">
          <el-button type="primary" @click="saveResume" :loading="isSaving">保存简历</el-button>
          <el-button>预览/导出</el-button>
        </div>
      </el-aside>

      <!-- 右侧内容编辑区 -->
      <el-main class="editor-main" @scroll="handleScroll">
        <!-- 基本信息 -->
        <div id="basic-info" class="resume-section">
          <el-card>
            <template #header><div class="section-header"><h3>基本信息</h3></div></template>
            <el-form :model="resumeData" label-width="80px">
              <el-row :gutter="20">
                <el-col :span="12"><el-form-item label="姓名"><el-input v-model="resumeData.full_name" /></el-form-item></el-col>
                <el-col :span="12"><el-form-item label="期望职位"><el-input v-model="resumeData.job_title" /></el-form-item></el-col>
                <el-col :span="12"><el-form-item label="电话"><el-input v-model="resumeData.phone" /></el-form-item></el-col>
                <el-col :span="12"><el-form-item label="邮箱"><el-input v-model="resumeData.email" /></el-form-item></el-col>
                <el-col :span="12"><el-form-item label="城市"><el-input v-model="resumeData.city" /></el-form-item></el-col>
                <el-col :span="24"><el-form-item label="个人总结"><el-input v-model="resumeData.summary" type="textarea" :rows="3" /></el-form-item></el-col>
              </el-row>
            </el-form>
          </el-card>
        </div>
        
        <!-- 教育背景 -->
        <div id="education" class="resume-section">
          <EducationEditor 
            v-if="resumeData.id"
            :resume-id="resumeData.id" 
            :initial-data="resumeData.educations || []"
            @change="fetchResumeData(resumeData.id!)"
          />
        </div>

        <!-- 工作经历 (占位) -->
        <div id="work-experience" class="resume-section">
            <el-card>
                <template #header>
                    <div class="section-header">
                        <h3>工作经历 (待开发)</h3>
                        <el-button type="primary" icon="Plus" circle />
                    </div>
                </template>
                <el-empty description="暂无工作经历" />
            </el-card>
        </div>
      </el-main>
    </el-container>
    <el-skeleton :rows="10" animated v-if="loading" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRoute } from 'vue-router';
import { getStructuredResumeApi, type StructuredResume } from '@/api/modules/resumeEditor';
import { updateResumeApi } from '@/api/modules/resume';
import EducationEditor from '@/components/resume/EducationEditor.vue';
import { ElMessage } from 'element-plus';
import { User, Reading, Briefcase } from '@element-plus/icons-vue';

const route = useRoute();
const loading = ref(true);
const isSaving = ref(false);
const activeSection = ref('basic-info');
const resumeData = ref<Partial<StructuredResume>>({
  title: '',
  full_name: '',
  job_title: '',
  phone: '',
  email: '',
  city: '',
  summary: '',
  educations: [],
  work_experiences: [],
  project_experiences: [],
  skills: [],
});

const fetchResumeData = async (id: number) => {
  loading.value = true;
  try {
    const data = await getStructuredResumeApi(id);
    resumeData.value = data;
  } catch (error) {
    console.error("获取简历详情失败", error);
    ElMessage.error("获取简历详情失败");
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  const resumeId = Number(route.params.id);
  if (resumeId) {
    fetchResumeData(resumeId);
  } else {
      loading.value = false;
      ElMessage.error("无效的简历ID");
  }
});

const saveResume = async () => {
  if (!resumeData.value.id) return;
  isSaving.value = true;
  try {
    const dataToUpdate = {
      title: resumeData.value.title,
      full_name: resumeData.value.full_name,
      job_title: resumeData.value.job_title,
      phone: resumeData.value.phone,
      email: resumeData.value.email,
      city: resumeData.value.city,
      summary: resumeData.value.summary,
    };
    await updateResumeApi(resumeData.value.id, dataToUpdate);
    ElMessage.success('简历主信息保存成功！');
  } catch (error) {
    ElMessage.error('保存失败');
  } finally {
      isSaving.value = false;
  }
};

const handleSectionSelect = (index: string) => {
  const element = document.getElementById(index);
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

const handleScroll = (event: Event) => {
    const mainEl = event.target as HTMLElement;
    const sections = ['basic-info', 'education', 'work-experience'];
    let currentSection = '';

    for (const id of sections) {
        const el = document.getElementById(id);
        if (el) {
            // 如果 section 的顶部进入了视口的上半部分
            if (el.getBoundingClientRect().top < window.innerHeight / 2) {
                currentSection = id;
            }
        }
    }
    if (currentSection) {
        activeSection.value = currentSection;
    }
};
</script>

<style scoped>
.editor-container {
  /* 减去Layout的Header高度(60px)和上下padding(40px) */
  height: calc(100vh - 60px); 
  padding: 0;
  margin: 0;
  max-width: 100%;
}
.editor-layout {
  height: 100%;
  background-color: #fff;
}
.editor-aside {
  background-color: #f5f7fa;
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e4e7ed;
}
.resume-title-display {
  text-align: center;
  margin-bottom: 20px;
  padding: 0 15px;
  font-weight: 600;
  font-size: 1.1rem;
}
.el-menu {
  background-color: transparent;
  border-right: none;
}
.aside-footer {
  margin-top: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.editor-main {
  padding: 20px 40px;
  height: 100%;
  overflow-y: auto;
}
.resume-section {
  margin-bottom: 20px;
}
.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.section-header h3 {
  margin: 0;
  font-size: 1.2rem;
}
</style>