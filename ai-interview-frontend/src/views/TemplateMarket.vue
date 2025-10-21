<template>
  <div class="template-market-container p-8">
    <h1 class="text-3xl font-bold mb-6">简历模板市场</h1>
    <div v-if="templateStore.isLoading" v-loading="true" style="height: 300px;"></div>
    <el-row :gutter="20" v-else>
      <el-col
        v-for="template in templateStore.templates"
        :key="template.id"
        :xs="24" :sm="12" :md="8" :lg="6"
        class="mb-5"
      >
        <el-card shadow="hover" :body-style="{ padding: '0px' }">
          <img :src="template.preview_image" class="w-full h-auto object-cover" style="aspect-ratio: 3/4;" />
          <div class="p-4">
            <h3 class="font-semibold">{{ template.name }}</h3>
            <p class="text-sm text-gray-500 mt-1 h-10 overflow-hidden">{{ template.description }}</p>
            <div class="mt-4 flex justify-end">
              <el-button type="primary" @click="useThisTemplate(template)">使用此模板</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useTemplateStore } from '@/store/modules/template';
import type { ResumeTemplateItem } from '@/api/modules/template';
import { ElRow, ElCol, ElCard, ElButton } from 'element-plus';
import { useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor'; // 假设

const templateStore = useTemplateStore();
const router = useRouter();
const editorStore = useResumeEditorStore(); // 假设

onMounted(() => {
  templateStore.fetchTemplates();
});

const useThisTemplate = (template: ResumeTemplateItem) => {
  // 这里的逻辑可以更复杂，例如询问用户是想覆盖当前简历还是新建
  // 简化版：直接应用到编辑器，并跳转回去
  // 您需要确保 editorStore 有这个 action
  editorStore.applyTemplateStructure(template.structure_json); 
  
  // 假设您有一个 resumeId 在 store 中
  const resumeId = editorStore.resumeMeta?.id;
  if (resumeId) {
    router.push({ name: 'ResumeEditor', params: { id: resumeId } });
  } else {
    // 或者跳转到简历列表页去新建
    router.push({ name: 'ResumeManagement' });
  }
};
</script>