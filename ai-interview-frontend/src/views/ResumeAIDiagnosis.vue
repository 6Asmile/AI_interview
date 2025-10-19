<!-- src/views/ResumeAIDiagnosis.vue -->
<template>
  <div class="page-container diagnosis-page">
    <div class="diagnosis-card">
      <h1 class="title">AI 简历智能诊断</h1>
      <p class="subtitle">上传您的简历文件，获取 AI 专业分析和优化建议</p>
      
      <!-- 【核心修复】为 el-upload 添加 name 属性，虽然 action="#" 但最好有 -->
      <el-upload
        ref="uploadRef"
        name="file"
        drag
        action="#"
        :http-request="handleUpload"
        :limit="1"
        :on-exceed="handleExceed"
        :auto-upload="false"
        :on-change="handleFileChange"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽文件至此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .pdf, .docx 格式，文件大小不超过 5MB
          </div>
        </template>
      </el-upload>

      <el-button 
        type="primary" 
        size="large" 
        class="upload-button"
        @click="submitUpload" 
        :loading="isAnalyzing"
        :disabled="!fileToUpload"
      >
        {{ isAnalyzing ? '正在分析...' : '上传并分析' }}
      </el-button>
    </div>
    <!-- 模板中不再有抽屉的引用，语法正确 -->
  </div>
</template>

<script setup lang="ts">
// --- 【核心修复】从 'vue' 中导入 nextTick ---
import { ref, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElUpload } from 'element-plus';
import type { UploadInstance, UploadProps, UploadRawFile, UploadFile } from 'element-plus';
import { UploadFilled } from '@element-plus/icons-vue';
import { genFileId } from 'element-plus';
import { createResumeApi } from '@/api/modules/resume';
import { analyzeResumeApi } from '@/api/modules/resumeEditor';

const router = useRouter();
const uploadRef = ref<UploadInstance>();
const fileToUpload = ref<UploadFile | null>(null);
const isAnalyzing = ref(false);

const handleFileChange: UploadProps['onChange'] = (uploadFile, uploadFiles) => {
  // 校验逻辑
  const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  if (uploadFile.raw && !allowedTypes.includes(uploadFile.raw.type)) {
    ElMessage.error('只支持 PDF 和 DOCX 格式!');
    uploadRef.value?.clearFiles();
    fileToUpload.value = null;
    return;
  }
  const isLt5M = (uploadFile.size || 0) / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error('文件大小不能超过 5MB!');
    uploadRef.value?.clearFiles();
    fileToUpload.value = null;
    return;
  }
  // --- 【核心修复】直接从事件参数中获取当前文件 ---
  // onChange 事件会在文件列表变化时触发，uploadFiles 是最新的列表
  fileToUpload.value = uploadFiles.length > 0 ? uploadFiles[uploadFiles.length - 1] : null;
};

const handleExceed: UploadProps['onExceed'] = (files) => {
  uploadRef.value?.clearFiles();
  const file = files[0] as UploadRawFile;
  file.uid = genFileId();
  uploadRef.value?.handleStart(file);
  // 【核心修复】在 nextTick 后，我们仍然从 handleFileChange 更新的 fileToUpload 获取文件
  // 这里的逻辑主要是为了 UI 上的替换效果
};

const submitUpload = () => {
  if (!fileToUpload.value) {
    ElMessage.warning('请先选择一个文件');
    return;
  }
  uploadRef.value?.submit();
};

const handleUpload = async () => {
  if (!fileToUpload.value?.raw) {
    ElMessage.warning('上传请求触发，但没有找到文件。');
    return;
  }
  
  isAnalyzing.value = true;
  try {
    const formData = new FormData();
    formData.append('file', fileToUpload.value.raw);
    const tempTitle = fileToUpload.value.name.replace(/\.[^/.]+$/, "");
    formData.append('title', `AI诊断-${tempTitle}`);
    const newResume = await createResumeApi(formData);
    
    const genericJd = "依据岗位匹配度优先原则，对该简历开展专业级通用性评估，重点分析其在‘目标岗位关键词匹配度’‘职业经历 STAR 法则应用’‘个人价值量化呈现’三方面的表现亮点与短板，同步提供可落地的经历描述优化、模块优先级调整及视觉呈现规范方案。";
    const newReport = await analyzeResumeApi(newResume.id, genericJd);

    ElMessage.success('分析完成，正在跳转到报告页面...');
    router.push({ 
      name: 'AnalysisReportDetail', 
      params: { reportId: newReport.id } 
    });

  } catch (error) {
    ElMessage.error('分析失败，请稍后重试');
    console.error(error);
  } finally {
    isAnalyzing.value = false;
    // 清理文件
    uploadRef.value?.clearFiles();
    fileToUpload.value = null;
  }
};
</script>

<style scoped>
.diagnosis-page { display: flex; justify-content: center; align-items: flex-start; padding-top: 50px; }
.diagnosis-card { width: 100%; max-width: 600px; padding: 40px; background-color: #fff; border-radius: 8px; text-align: center; box-shadow: var(--el-box-shadow-light); }
.title { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
.subtitle { color: #999; margin-bottom: 30px; }
.upload-button { margin-top: 30px; width: 50%; }
</style>