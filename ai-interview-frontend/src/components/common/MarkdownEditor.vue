<template>
  <MdEditor
    v-model="text"
    :theme="theme"
    @onUploadImg="handleUploadImage"
    style="height: 100%; border: none;"
  />
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { MdEditor } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { ElMessage } from 'element-plus';
import { uploadAvatarApi } from '@/api/modules/user';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue']);

const text = ref(props.modelValue);
const theme = ref<'light' | 'dark'>('light'); // 简单实现一个主题，可以后续扩展

watch(() => props.modelValue, (newValue) => {
  if (newValue !== text.value) {
    text.value = newValue;
  }
});

watch(text, (newValue) => {
  emit('update:modelValue', newValue);
});

const handleUploadImage = async (files: File[], callback: (urls: string[]) => void) => {
  if (files.length === 0) return;
  
  const uploadPromises = files.map(async (file) => {
    const formData = new FormData();
    formData.append('avatar', file); // 复用上传接口
    try {
      const res = await uploadAvatarApi(formData);
      return res.avatar_url;
    } catch (error) {
      ElMessage.error(`图片 ${file.name} 上传失败`);
      return null;
    }
  });

  const urls = (await Promise.all(uploadPromises)).filter(url => url !== null) as string[];
  callback(urls);
};
</script>