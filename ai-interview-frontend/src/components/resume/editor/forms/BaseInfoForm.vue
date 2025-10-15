<!-- src/components/resume/editor/forms/BaseInfoForm.vue -->
<template>
  <el-form label-position="top">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-form-item label="姓名"><el-input v-model="props.name" /></el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="头像">
          <el-upload
            class="avatar-uploader"
            action="#"
            :show-file-list="false"
            :http-request="handleAvatarUpload"
            :before-upload="beforeAvatarUpload"
          >
            <!-- 【核心修复】直接使用 props.photo 作为 src -->
            <img v-if="props.photo" :src="props.photo" class="avatar" />
            <el-icon v-else class="avatar-uploader-icon"><Plus /></el-icon>
          </el-upload>
        </el-form-item>
      </el-col>
    </el-row>
    <div v-for="(item, index) in props.items" :key="item.id" class="list-item-form">
      <el-input v-model="item.label" placeholder="标签" />
      <el-input v-model="item.value" placeholder="内容" />
      <el-button link type="danger" :icon="Delete" @click="removeItem('items', index)" />
    </div>
    <el-button plain type="primary" @click="addItem('items')">添加信息</el-button>
  </el-form>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import { ElMessage } from 'element-plus';
import { Plus, Delete } from '@element-plus/icons-vue';
import type { UploadRequestOptions, UploadProps } from 'element-plus';
// 【核心修复】导入我们封装好的 request 实例，而不是原生的 axios
import request from '@/api/request'; 

const { module } = defineProps<{ module: any }>();
const props = computed(() => module.props);

const newItemTemplates: Record<string, object> = {
  items: { label: '新条目', value: '新内容' },
};

const fullAvatarUrl = computed(() => {
    if (!props.value.photo) return '';
    if (props.value.photo.startsWith('http') || props.value.photo.startsWith('blob:')) {
        return props.value.photo;
    }
    const baseUrl = import.meta.env.VITE_API_BASE_URL.split('/api/v1')[0];
    return `${baseUrl}${props.value.photo}`;
});

const handleAvatarUpload = async (options: UploadRequestOptions) => {
  // 【核心修复】上传成功后，直接使用后端返回的相对路径
  // 预览时，让 BaseInfoModule 组件去拼接完整 URL
  const formData = new FormData();
  formData.append('file', options.file);
  formData.append('dir', 'avatars');
  
  try {
    const response: { file_url: string } = await request({
        url: '/upload/',
        method: 'post',
        data: formData,
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    props.value.photo = response.file_url; // 更新为相对路径 /media/avatars/...
    ElMessage.success('头像上传成功');
  } catch (error) {
    ElMessage.error('头像上传失败');
  }
};

// 【核心修复】在 beforeUpload 中，使用 URL.createObjectURL 实现本地实时预览
const beforeAvatarUpload: UploadProps['beforeUpload'] = (rawFile) => {
  if (rawFile.type !== 'image/jpeg' && rawFile.type !== 'image/png') {
    ElMessage.error('头像只能是 JPG/PNG 格式!');
    return false;
  }
  if (rawFile.size / 1024 / 1024 > 2) {
    ElMessage.error('头像大小不能超过 2MB!');
    return false;
  }
  // 关键：在上传前，将本地文件转为 blob URL 并赋值给 props.photo
  // 这样无需等待上传完成，即可在左侧表单和右侧画布中实时看到预览图
  props.value.photo = URL.createObjectURL(rawFile);
  return true;
};

const addItem = (propKey: string) => {
  if (props.value[propKey]) {
    props.value[propKey].push({ id: uuidv4(), ...newItemTemplates[propKey] });
  }
};
const removeItem = (propKey: string, index: number) => {
  if (props.value[propKey]) {
    props.value[propKey].splice(index, 1);
  }
};
</script>

<style>
/* 样式保持不变 */
.avatar-uploader .el-upload { border: 1px dashed var(--el-border-color); border-radius: 6px; cursor: pointer; position: relative; overflow: hidden; transition: var(--el-transition-duration-fast); }
.avatar-uploader .el-upload:hover { border-color: var(--el-color-primary); }
.avatar-uploader-icon { font-size: 28px; color: #8c939d; width: 100px; height: 100px; text-align: center; }
.avatar { width: 100px; height: 100px; display: block; object-fit: cover; }
.list-item-form { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
</style>