<!-- src/components/common/RichTextEditor.vue -->
<template>
  <div class="rich-text-editor-wrapper">
    <Toolbar
      :editor="editorRef"
      :defaultConfig="toolbarConfig"
      :mode="mode"
      style="border-bottom: 1px solid #ccc"
    />
    <Editor
      :defaultConfig="editorConfig"
      :mode="mode"
      v-model="valueHtml"
      style="height: 150px; overflow-y: hidden"
      @onCreated="handleCreated"
      @onChange="handleChange"
    />
  </div>
</template>

<script setup lang="ts">
import '@wangeditor/editor/dist/css/style.css';
import { onBeforeUnmount, shallowRef, computed } from 'vue';
import { Editor, Toolbar } from '@wangeditor/editor-for-vue';
import type { IToolbarConfig, IEditorConfig } from '@wangeditor/editor';

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  }
});

const emit = defineEmits(['update:modelValue']);

const editorRef = shallowRef();
const mode = 'default';

const toolbarConfig: Partial<IToolbarConfig> = {
  toolbarKeys: [
    'bold', 'underline', 'italic', '|',
    'numberedList', 'bulletedList', '|',
    'undo', 'redo',
  ],
};

const editorConfig: Partial<IEditorConfig> = {
  placeholder: '请输入内容...',
  MENU_CONF: {},
};

const valueHtml = computed({
    get() {
        return props.modelValue;
    },
    // 【核心修复】使用下划线前缀表示该参数是故意未使用的
    set(_val) {
        // v5 的 v-model 会自动触发 update, 
        // 但为了确保在任何情况下数据都能正确同步，我们主要依赖 onChange 事件。
        // set 函数在这里主要是为了满足 computed 的完整结构。
    }
});

const handleCreated = (editor: any) => {
  editorRef.value = editor;
};

const handleChange = (editor: any) => {
    emit('update:modelValue', editor.getHtml());
};

onBeforeUnmount(() => {
  const editor = editorRef.value;
  if (editor == null) return;
  editor.destroy();
});
</script>

<style scoped>
.rich-text-editor-wrapper { border: 1px solid var(--el-border-color); border-radius: 4px; z-index: 100; }
.rich-text-editor-wrapper :deep(.w-e-toolbar) { z-index: 101 !important; }
.rich-text-editor-wrapper :deep(.w-e-text-container) { z-index: 100 !important; }
</style>