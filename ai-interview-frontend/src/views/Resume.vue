<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>我的简历</span>
          <div>
            <el-dropdown @command="handleCreateCommand">
              <el-button type="primary">
                新建简历 <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="online">在线创建新简历</el-dropdown-item>
                  <el-dropdown-item command="upload">上传简历文件</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <el-table :data="resumeList" v-loading="isLoading">
        <el-table-column prop="title" label="简历标题" />
        <el-table-column prop="status" label="状态">
          <template #default="scope">
            <el-tag :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="最后更新时间">
           <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="scope">
            <el-button
              v-if="isOnlineResume(scope.row.status)"
              type="primary"
              size="small"
              @click="handleEdit(scope.row)"
            >
              编辑
            </el-button>
            <el-button size="small" @click="handlePreview(scope.row)">预览</el-button>
            <el-button type="danger" size="small" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="uploadDialogVisible" title="上传简历文件" width="500px" @close="resetUploadForm">
      <el-form :model="uploadForm" ref="uploadFormRef" label-width="80px">
        <el-form-item label="简历标题" prop="title">
          <el-input v-model="uploadForm.title" placeholder="可选，默认为文件名"></el-input>
        </el-form-item>
        <el-form-item label="选择文件" prop="file" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-exceed="handleExceed"
            :on-change="handleFileChange"
            accept=".pdf,.doc,.docx"
          >
            <template #trigger>
              <el-button type="primary">选择文件</el-button>
            </template>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 PDF, DOC, DOCX 格式，且文件大小不超过 5MB.
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmUpload" :loading="isUploading">
          {{ isUploading ? '解析中...' : '确定上传' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { getResumeListApi, deleteResumeApi, createResumeApi } from '@/api/modules/resume';
import type { ResumeItem } from '@/api/modules/resume';
import { ElMessage, ElMessageBox, type UploadFile, type UploadInstance } from 'element-plus';
import { ArrowDown } from '@element-plus/icons-vue';
import { formatDate } from '@/utils/format';

const router = useRouter();
const resumeList = ref<ResumeItem[]>([]);
const isLoading = ref(false);

const uploadDialogVisible = ref(false);
const isUploading = ref(false);
const uploadRef = ref<UploadInstance>();
const uploadForm = reactive({
  title: '',
  file: null as File | null,
});

const statusText = (status: string) => {
  const map: Record<string, string> = {
    draft: '草稿',
    published: '已发布',
    parsed: '已解析',
    failed: '解析失败'
  };
  return map[status] || '未知';
};

const statusType = (status: string) => {
  const map: Record<string, any> = {
    draft: 'info',
    published: 'success',
    parsed: 'success',
    failed: 'danger'
  };
  return map[status] || '';
};

const isOnlineResume = (status: string) => {
  return status === 'draft' || status === 'published';
};

const fetchResumes = async () => {
  isLoading.value = true;
  try {
    resumeList.value = await getResumeListApi();
  } catch (error) {
    ElMessage.error('获取简历列表失败');
  } finally {
    isLoading.value = false;
  }
};

const handleCreateCommand = async (command: 'online' | 'upload') => {
  if (command === 'online') {
    try {
      const title = `我的在线简历-${new Date().toLocaleDateString()}`;
      const newResume = await createResumeApi({ title, status: 'draft' });
      ElMessage.success('在线简历创建成功，即将进入编辑模式...');
      router.push({ name: 'ResumeEditor', params: { id: newResume.id } });
    } catch (error) {
      ElMessage.error('创建在线简历失败');
    }
  } else {
    uploadDialogVisible.value = true;
  }
};

const handleEdit = (row: ResumeItem) => {
  router.push({ name: 'ResumeEditor', params: { id: row.id } });
};

const handleDelete = async (row: ResumeItem) => {
  await ElMessageBox.confirm(`确定要删除简历 "${row.title}" 吗？`, '提示', {
    type: 'warning',
  });
  try {
    await deleteResumeApi(row.id);
    ElMessage.success('删除成功');
    fetchResumes();
  } catch (error) {
    ElMessage.error('删除失败');
  }
};

const handlePreview = (row: ResumeItem) => {
  const isUploadedFile = row.status === 'parsed' || row.status === 'failed';
  
  if (isUploadedFile && row.file_url) {
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    const domain = baseUrl.replace('/api/v1', '');
    window.open(`${domain}${row.file_url}`, '_blank');
  } else if (isOnlineResume(row.status)) {
    const routeData = router.resolve({ name: 'ResumePreview', params: { id: row.id } });
    window.open(routeData.href, '_blank');
  } else {
    ElMessage.info('该简历没有可预览的内容。');
  }
};

const resetUploadForm = () => {
  uploadForm.title = '';
  uploadForm.file = null;
  uploadRef.value?.clearFiles();
};

const handleExceed = () => {
  ElMessage.warning('只能选择一个文件，请先移除已有文件');
};

const handleFileChange = (file: UploadFile) => {
  if (file.raw) {
    uploadForm.file = file.raw;
  }
};

const handleConfirmUpload = async () => {
  if (!uploadForm.file) {
    ElMessage.error('请选择要上传的文件');
    return;
  }
  isUploading.value = true;
  try {
    const formData = new FormData();
    formData.append('file', uploadForm.file);
    if (uploadForm.title) {
      formData.append('title', uploadForm.title);
    }
    await createResumeApi(formData);
    ElMessage.success('上传成功，简历正在后台解析...');
    uploadDialogVisible.value = false;
    fetchResumes();
  } catch (error) {
    ElMessage.error('上传或解析失败，请检查文件格式或联系管理员');
  } finally {
    isUploading.value = false;
  }
};

onMounted(() => {
  fetchResumes();
});
</script>

<style scoped>
/* 样式保持不变 */
</style>