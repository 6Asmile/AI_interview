<!-- src/components/common/DiffViewer.vue -->
<template>
  <div class="diff-viewer-container">
    <div class="diff-legend">
      <span class="legend-item added">新增内容</span>
      <span class="legend-item deleted">删除内容</span>
    </div>
    <div class="diff-content" v-html="diffHtml"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
// --- 【核心修复】使用默认导入 ---
import diff_match_patch, { DIFF_DELETE, DIFF_INSERT, DIFF_EQUAL } from 'diff-match-patch';

const props = defineProps({
  oldText: {
    type: String,
    required: true,
  },
  newText: {
    type: String,
    required: true,
  },
});

const diffHtml = computed(() => {
  // --- 【核心修复】使用导入的 diff_match_patch 来实例化 ---
  const dmp = new diff_match_patch();
  const diffs = dmp.diff_main(htmlToText(props.oldText), htmlToText(props.newText));
  dmp.diff_cleanupSemantic(diffs);

  let html = '';
  for (const [op, data] of diffs) {
    const text = data.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
    switch (op) {
      case DIFF_INSERT:
        html += `<span class="diff-added">${text}</span>`;
        break;
      case DIFF_DELETE:
        html += `<span class="diff-deleted">${text}</span>`;
        break;
      case DIFF_EQUAL:
        html += `<span>${text}</span>`;
        break;
    }
  }
  return html;
});

const htmlToText = (html: string): string => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    return tempDiv.textContent || tempDiv.innerText || '';
};

</script>

<style scoped>
.diff-viewer-container { border: 1px solid #e0e0e0; border-radius: 4px; padding: 16px; background-color: #f9f9f9; font-family: 'Courier New', Courier, monospace; line-height: 1.6; }
.diff-legend { margin-bottom: 12px; font-family: sans-serif; font-size: 12px; }
.legend-item { margin-right: 16px; padding: 2px 6px; border-radius: 3px; }
.added { background-color: #ddfbe6; color: #278342; }
.deleted { background-color: #fce8e8; color: #c73737; text-decoration: line-through; }
.diff-content { white-space: pre-wrap; word-break: break-all; }
:deep(.diff-added) { background-color: #e6ffec; text-decoration: none; }
:deep(.diff-deleted) { background-color: #ffebe9; text-decoration: line-through; }
</style>