<template>
  <div class="preview-page-container" v-loading="isLoading">
    <div v-if="resumeData">
      <ResumePreviewTemplate :resume-data="resumeData" />
    </div>
    <el-empty v-else-if="!isLoading" description="无法加载简历数据"></el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { getStructuredResumeApi } from '@/api/modules/resumeEditor';
import type { StructuredResume } from '@/api/modules/resume';
import ResumePreviewTemplate from '@/components/resume/ResumePreview.vue'; // 复用之前的预览模板

const route = useRoute();
const isLoading = ref(true);
const resumeData = ref<StructuredResume | null>(null);

onMounted(async () => {
  const resumeId = Number(route.params.id);
  if (resumeId) {
    try {
      resumeData.value = await getStructuredResumeApi(resumeId);
    } catch (error) {
      console.error("获取简历失败", error);
    } finally {
      isLoading.value = false;
    }
  } else {
    isLoading.value = false;
  }
});
</script>

<style scoped>
.preview-page-container {
  display: flex;
  justify-content: center;
  background-color: #f0f2f5;
  padding: 20px;
  min-height: 100vh;
}
</style>