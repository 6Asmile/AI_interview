<template>
  <el-dialog
    v-model="dialogVisible"
    title="简历预览"
    width="880px"
    top="5vh"
    @close="handleClose"
  >
    <div v-loading="isLoading" class="preview-container">
      <el-scrollbar>
        <!-- 如果是在线简历，使用预览组件 -->
        <ResumePreview v-if="resumeData && isOnlineResume(resumeData.status)" :resume-data="resumeData" />
        <!-- 如果是上传的简历，显示解析后的文本 -->
        <div v-else-if="resumeData" class="parsed-content">
          <h3>{{ resumeData.title }} (解析内容)</h3>
          <pre>{{ resumeData.parsed_content }}</pre>
        </div>
        <div v-else class="loading-error">
          无法加载简历数据。
        </div>
      </el-scrollbar>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor'; // 复用这个API
import type { StructuredResume } from '@/api/modules/resume';
import ResumePreview from '@/components/resume/ResumePreview.vue'; // 复用编辑器里的预览组件

const props = defineProps<{
  modelValue: boolean; // 用于 v-model
  resumeId: number | null;
}>();

const emit = defineEmits(['update:modelValue']);

const dialogVisible = ref(props.modelValue);
const isLoading = ref(false);
const resumeData = ref<StructuredResume | null>(null);

const isOnlineResume = (status: string) => status === 'draft' || status === 'published';

const fetchResumeDetail = async (id: number) => {
  isLoading.value = true;
  resumeData.value = null;
  try {
    // 后端获取单个简历的接口会返回完整数据
    const data = await getStructuredResumeApi(id);
    resumeData.value = data;
  } catch (error) {
    console.error("获取简历详情失败", error);
  } finally {
    isLoading.value = false;
  }
};

watch(() => props.modelValue, (val) => {
  dialogVisible.value = val;
  if (val && props.resumeId) {
    fetchResumeDetail(props.resumeId);
  }
});

const handleClose = () => {
  emit('update:modelValue', false);
};
</script>

<style scoped>
.preview-container {
  height: 75vh;
  background-color: #f0f2f5;
}
.parsed-content {
  padding: 20px;
  background-color: #fff;
  white-space: pre-wrap; /* 自动换行 */
  word-wrap: break-word;
  line-height: 1.7;
  font-family: 'Courier New', Courier, monospace;
}
.loading-error {
  text-align: center;
  padding-top: 50px;
  color: #909399;
}
</style>