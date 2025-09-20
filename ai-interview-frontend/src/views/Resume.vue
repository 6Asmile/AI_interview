<!-- src/views/Resume.vue -> <template> -->
<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>我的简历</span>
          <el-button type="primary" @click="handleOpenUploadDialog">上传新简历</el-button>
        </div>
      </template>

      <el-table :data="resumeList" v-loading="loading" style="width: 100%" empty-text="您还没有上传任何简历">
        <el-table-column prop="title" label="简历标题" />
        <el-table-column prop="file_type" label="文件类型" width="120" />
        <el-table-column prop="status" label="解析状态" width="120">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="200">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="handleView(scope.row)">查看</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="上传新简历" width="500" @close="handleDialogClose">
      <el-form ref="uploadFormRef" :model="uploadForm" :rules="uploadRules" label-width="100px">
        <el-form-item label="简历标题" prop="title">
          <el-input v-model="uploadForm.title" placeholder="如果留空，将使用文件名作为标题" />
        </el-form-item>
        <el-form-item label="选择文件" prop="file">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-exceed="handleExceed"
            accept=".pdf,.doc,.docx"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">仅支持 PDF, DOC, DOCX 格式，且文件大小不超过 5MB.</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirmUpload" :loading="uploading">确定上传</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

// src/views/Resume.vue -> <script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules, UploadInstance, UploadFile } from 'element-plus';
import { createResumeApi, deleteResumeApi, getResumeListApi, type ResumeItem } from '@/api/modules/resume';

const loading = ref(false);
const uploading = ref(false);
const dialogVisible = ref(false);
const resumeList = ref<ResumeItem[]>([]);

const uploadFormRef = ref<FormInstance>();
const uploadRef = ref<UploadInstance>();

const uploadForm = reactive({
  title: '',
  file: null as File | null,
});

const uploadRules = reactive<FormRules>({
  file: [{ required: true, message: '请选择要上传的简历文件' }],
});

// --- 核心逻辑 ---

const fetchResumes = async () => {
  loading.value = true;
  try {
    const res = await getResumeListApi();
    resumeList.value = res;
  } catch (error) {
    console.error('获取简历列表失败', error);
  } finally {
    loading.value = false;
  }
};
onMounted(() => { fetchResumes(); });

const handleFileChange = (uploadFile: UploadFile, _uploadFiles: UploadFile[]) => {
  const rawFile = uploadFile.raw;
  if (!rawFile) return;

  const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  if (!allowedTypes.includes(rawFile.type)) {
    ElMessage.error('仅支持 PDF, DOC, DOCX 格式!');
    uploadRef.value?.clearFiles();
    return;
  }
  if (rawFile.size / 1024 / 1024 > 5) {
    ElMessage.error('文件大小不能超过 5MB!');
    uploadRef.value?.clearFiles();
    return;
  }
  
  uploadForm.file = rawFile;
  uploadFormRef.value?.validateField('file'); // 手动触发校验
};

const handleExceed = () => {
  ElMessage.warning('只能上传一个文件');
};

const handleConfirmUpload = async () => {
  if (!uploadFormRef.value) return;
  await uploadFormRef.value.validate(async (valid) => {
    if (valid && uploadForm.file) {
      uploading.value = true;
      
      const formData = new FormData();
      formData.append('file', uploadForm.file);
      if (uploadForm.title) {
        formData.append('title', uploadForm.title);
      }

      try {
        await createResumeApi(formData);
        ElMessage.success('简历上传并解析成功！');
        dialogVisible.value = false;
        await fetchResumes();
      } catch (error) {
        console.error('上传简历失败', error);
        ElMessage.error('上传简历失败，请稍后再试');
      } finally {
        uploading.value = false;
      }
    }
  });
};

const handleDialogClose = () => {
  uploadFormRef.value?.resetFields();
  uploadRef.value?.clearFiles();
  uploadForm.file = null;
};

const handleOpenUploadDialog = () => {
  dialogVisible.value = true;
};

// --- 辅助函数 (保持不变或更新) ---
const formatTime = (timeStr: string) => new Date(timeStr).toLocaleString();
const handleView = (row: ResumeItem) => {
  window.open(row.file, '_blank');
};
const handleDelete = async (row: ResumeItem) => {
  ElMessageBox.confirm(`您确定要删除简历 "${row.title}" 吗？`, '警告', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      try {
        await deleteResumeApi(row.id);
        ElMessage.success('删除成功');
        await fetchResumes();
      } catch (error) {
        console.error('删除失败', error);
      }
    })
    .catch(() => {
      ElMessage.info('已取消删除');
    });
};
const statusText = (status: string) => ({ pending: '待解析', parsed: '已解析', failed: '解析失败' }[status] || '未知');
const statusTagType = (status: string) => ({ pending: 'warning', parsed: 'success', failed: 'danger' }[status] || 'info');

// 把不变的函数完整复制过来
// fetchResumes, handleDelete
</script>

<style scoped>
.resume-uploader {
  width: 100%;
}
</style>