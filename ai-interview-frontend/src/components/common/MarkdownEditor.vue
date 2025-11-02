<template>
  <MdEditor
    v-model="text"
    :theme="theme"
    @onUploadImg="handleUploadImage"
    @onGetCatalog="emit('onGetCatalog', $event)"
    style="height: 100%; border: none;"
  />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
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

// 【核心修正】在 emits 中声明 onGetCatalog 事件
const emit = defineEmits(['update:modelValue', 'onGetCatalog']);

const text = ref(props.modelValue);
const theme = ref<'light' | 'dark'>('light');

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
    formData.append('avatar', file);
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