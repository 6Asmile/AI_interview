<!-- src/views/Resume.vue -->
<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>我的简历</span>
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
      </template>

      <el-table :data="resumeList" v-loading="isLoading" style="width: 100%">
        <el-table-column prop="title" label="简历标题" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="最后更新时间" width="200">
           <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button v-if="isOnlineResume(scope.row.status)" link type="primary" @click="handleEdit(scope.row.id)">编辑</el-button>
            <el-button link type="primary" @click="handlePreview(scope.row)">预览</el-button>
            <el-popconfirm title="确定要删除这份简历吗？" @confirm="handleDelete(scope.row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 文件上传对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传简历文件" width="500px" @close="resetUploadDialog">
      <!-- 【核心修改#2】增加标题输入框 -->
      <el-form-item label="简历标题">
        <el-input v-model="uploadForm.title" placeholder="请输入简历标题，默认为文件名"></el-input>
      </el-form-item>
      <el-upload
        ref="uploadRef"
        drag
        action="#"
        :http-request="handleUpload"
        :limit="1"
        :on-exceed="handleExceed"
        :auto-upload="false"
        :on-change="handleFileChange"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处或 <em>点击上传</em></div>
        <template #tip><div class="el-upload__tip">仅支持 PDF, DOC, DOCX 格式，大小不超过 5MB.</div></template>
      </el-upload>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitUpload" :loading="isUploading">
            {{ isUploading ? '解析中...' : '确定上传' }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { getResumeListApi, createResumeApi, deleteResumeApi, type ResumeItem } from '@/api/modules/resume';
import { ElMessage, ElPopconfirm, ElMessageBox } from 'element-plus';
import type { UploadInstance, UploadProps, UploadRawFile, UploadFile } from 'element-plus';
import { ArrowDown, UploadFilled } from '@element-plus/icons-vue';
import { genFileId } from 'element-plus';
import { formatDateTime } from '@/utils/format';

const router = useRouter();
const resumeList = ref<ResumeItem[]>([]);
const isLoading = ref(true);
const uploadDialogVisible = ref(false);
const isUploading = ref(false);
const uploadRef = ref<UploadInstance>();
// 【核心修改#2】使用 reactive 对象来管理上传表单
const uploadForm = reactive({
  title: '',
  file: null as UploadFile | null
});

const fetchResumeList = async () => {
  isLoading.value = true;
  try {
    resumeList.value = await getResumeListApi();
  } catch (error) { console.error(error); ElMessage.error('获取简历列表失败'); } 
  finally { isLoading.value = false; }
};

onMounted(fetchResumeList);

const handleDelete = async (id: number) => {
  try {
    await deleteResumeApi(id);
    ElMessage.success('删除成功');
    // 【优化】从列表中移除，而不是重新请求
    const index = resumeList.value.findIndex(r => r.id === id);
    if (index > -1) resumeList.value.splice(index, 1);
  } catch (error) { ElMessage.error('删除失败'); }
};

const isOnlineResume = (status: string): boolean => status === 'draft' || status === 'published';
const handleEdit = (id: number) => router.push({ name: 'ResumeEditor', params: { id } });
const handlePreview = (row: ResumeItem) => {
  // ... (此函数逻辑保持不变)
  if ((row.status === 'parsed' || row.status === 'failed') && row.file_url) {
    const baseUrl = import.meta.env.VITE_API_BASE_URL;
    if (!baseUrl) { ElMessage.error('系统配置错误，无法生成预览链接。'); return; }
    const domain = baseUrl.split('/api/v1')[0];
    window.open(`${domain}${row.file_url}`, '_blank');
  } else if (isOnlineResume(row.status)) {
    const routeData = router.resolve({ name: 'ResumePreview', params: { id: row.id } });
    window.open(routeData.href, '_blank');
  } else {
    ElMessage.info('该简历当前没有可预览的内容。');
  }
};

const handleCreateCommand = (command: string) => {
  if (command === 'online') handleCreateOnline();
  else if (command === 'upload') uploadDialogVisible.value = true;
};

// --- 【核心修改#1 & #2】创建与上传逻辑 ---

const handleCreateOnline = async () => {
  // 弹窗让用户输入标题
  ElMessageBox.prompt('请输入新简历的标题', '创建在线简历', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPattern: /\S/,
    inputErrorMessage: '标题不能为空',
  }).then(async ({ value }) => {
    try {
      const newResume = await createResumeApi({ title: value, status: 'draft' });
      // 【优化】直接将返回的数据添加到列表顶部
      resumeList.value.unshift(newResume);
      ElMessage.success('在线简历创建成功！');
      // 询问是否立即编辑
      ElMessageBox.confirm('是否立即跳转到编辑器？', '提示', {
        confirmButtonText: '立即跳转',
        cancelButtonText: '稍后',
        type: 'success'
      }).then(() => {
        router.push({ name: 'ResumeEditor', params: { id: newResume.id } });
      });
    } catch (error) { ElMessage.error('创建失败'); }
  }).catch(() => {
    ElMessage.info('已取消创建');
  });
};

const submitUpload = () => uploadRef.value?.submit();

const handleUpload = async () => {
  if (!uploadForm.file) { ElMessage.warning('请先选择文件'); return; }
  isUploading.value = true;
  const formData = new FormData();
  formData.append('file', uploadForm.file.raw!);
  // 如果用户输入了标题，就发送；否则后端会使用文件名
  if (uploadForm.title) formData.append('title', uploadForm.title);

  try {
    const newResume = await createResumeApi(formData);
    ElMessage.success('上传并解析成功！');
    // 【优化】直接将返回的数据添加到列表顶部
    resumeList.value.unshift(newResume);
    uploadDialogVisible.value = false;
  } catch (error) { ElMessage.error('上传或解析失败'); } 
  finally { isUploading.value = false; }
};

const handleFileChange: UploadProps['onChange'] = (uploadFile) => {
  uploadForm.file = uploadFile;
  // 如果用户未输入标题，则自动使用文件名（不含扩展名）填充
  if (!uploadForm.title && uploadFile.name) {
    uploadForm.title = uploadFile.name.replace(/\.[^/.]+$/, "");
  }
};

const handleExceed: UploadProps['onExceed'] = (files) => {
  uploadRef.value?.clearFiles();
  const file = files[0] as UploadRawFile;
  file.uid = genFileId();
  uploadRef.value?.handleStart(file);
};

const resetUploadDialog = () => {
  uploadForm.title = '';
  uploadForm.file = null;
  uploadRef.value?.clearFiles();
};

const statusText = (status: string) => ({ draft: '草稿', published: '已发布', parsed: '已解析', failed: '解析失败' }[status] || '未知');
const statusTagType = (status: string) => ({ draft: 'info', published: 'success', parsed: 'success', failed: 'danger' }[status] || 'info');
</script>

<style scoped>
/* 样式与之前保持一致 */
.page-container { padding: 20px; }
.page-card-header { display: flex; justify-content: space-between; align-items: center; }
</style>