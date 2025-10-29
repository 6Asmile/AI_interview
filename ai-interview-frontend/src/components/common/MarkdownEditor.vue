<template>
  <div class="markdown-editor-container border rounded-lg overflow-hidden">
    <!-- 工具栏 -->
    <div class="toolbar p-2 bg-gray-50 border-b">
      <!-- 简单实现几个常用功能，未来可扩展 -->
      <el-button-group>
        <el-button @click="togglePreview" :type="isPreviewing ? 'primary' : ''" :icon="View">
          {{ isPreviewing ? '返回编辑' : '实时预览' }}
        </el-button>
      </el-button-group>
    </div>

    <div class="editor-main-area flex" :style="{ height: editorHeight }">
      <!-- 编辑区 (Textarea) -->
      <textarea
        v-show="!isPreviewing"
        ref="textareaRef"
        v-model="internalContent"
        class="editor-textarea w-full h-full p-4 resize-none focus:outline-none font-mono text-sm leading-6"
        placeholder="开始创作你的文章..."
      ></textarea>

      <!-- 预览区 (MarkdownRenderer) -->
      <div v-show="isPreviewing" class="preview-area w-full h-full p-4 overflow-y-auto">
        <MarkdownRenderer :content="internalContent" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineProps, defineEmits, onMounted } from 'vue';
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue';
import { ElButton, ElButtonGroup } from 'element-plus';
import { View } from '@element-plus/icons-vue';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  height: {
    type: String,
    default: '600px',
  },
});

const emit = defineEmits(['update:modelValue']);

const textareaRef = ref<HTMLTextAreaElement | null>(null);
const isPreviewing = ref(false);

const internalContent = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value);
  },
});

const editorHeight = computed(() => props.height);

const togglePreview = () => {
  isPreviewing.value = !isPreviewing.value;
};

onMounted(() => {
  // 可以在这里集成更高级的编辑器功能，例如快捷键
});
</script>

<style scoped>
.editor-textarea {
  font-family: 'Courier New', Courier, monospace;
}
</style>