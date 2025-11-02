<template>
  <MdEditor
    v-model="text"
    :theme="theme"
    @onUploadImg="handleUploadImage"
    @onGetCatalog="emit('onGetCatalog', $event)"
    style="height: 100%; border: none;"
    :toolbars="toolbars"
  >
    <!-- 【核心修复】使用 defToolbars 插槽，并为我们的自定义工具栏项提供模板 -->
    <template #defToolbars>
      <Emoji @onInsert="insertContent" />
    </template>
  </MdEditor>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { MdEditor, type ToolbarNames } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { ElMessage } from 'element-plus';
import { uploadFileApi } from '@/api/modules/common';

import { Emoji } from '@vavt/v3-extension';
import '@vavt/v3-extension/lib/asset/style.css';


const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue', 'onGetCatalog']);

const text = ref(props.modelValue);
const theme = ref<'light' | 'dark'>('light');

// 【核心修复】1. 定义 toolbars 列表，并在其中加入一个自定义的插槽名称，以 'def' 开头
const toolbars: ToolbarNames[] = [
  'bold', 'underline', 'italic', 'strikeThrough', '-',
  'title', 'quote', 'unorderedList', 'orderedList', '-',
  'code', 'link', 'image', 'table', 'mermaid', 'katex',
  0, // <-- 使用数字 0 作为我们自定义插槽的占位符
  '-',
  'revoke', 'next', 'save', '=',
  'prettier', 'pageFullscreen', 'fullscreen', 'preview', 'htmlPreview', 'catalog', 'github'
];


watch(() => props.modelValue, (newValue) => {
  if (newValue !== text.value) {
    text.value = newValue;
  }
});

watch(text, (newValue) => {
  emit('update:modelValue', newValue);
});

// 插入内容的函数
const insertContent = (content: string) => {
  const textarea = document.querySelector('.md-editor-input');

  if (textarea) {
    const start = (textarea as HTMLTextAreaElement).selectionStart;
    const end = (textarea as HTMLTextAreaElement).selectionEnd;
    
    text.value = text.value.substring(0, start) + content + text.value.substring(end);

    (textarea as HTMLTextAreaElement).focus();
    const newPos = start + content.length;
    (textarea as HTMLTextAreaElement).selectionStart = newPos;
    (textarea as HTMLTextAreaElement).selectionEnd = newPos;
  } else {
    text.value += content;
  }
};


const handleUploadImage = async (files: File[], callback: (urls: string[]) => void) => {
  if (files.length === 0) return;
  const backendBaseUrl = import.meta.env.VITE_API_BASE_URL.replace('/api/v1', '');
  
  const uploadPromises = files.map(async (file) => {
    try {
      const res = await uploadFileApi(file, 'post_images');
      const fullUrl = `${backendBaseUrl}${res.file_url}`;
      return fullUrl;
    } catch (error) {
      ElMessage.error(`图片 ${file.name} 上传失败`);
      return null;
    }
  });

  const urls = (await Promise.all(uploadPromises)).filter(url => url !== null) as string[];
  callback(urls);
};
</script>