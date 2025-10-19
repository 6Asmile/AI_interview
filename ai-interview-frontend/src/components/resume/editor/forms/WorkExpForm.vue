<!-- src/components/resume/editor/forms/WorkExpForm.vue -->
<template>
  <div>
    <div v-for="(exp, index) in props.experiences" :key="exp.id" class="list-item-form-vertical">
      <el-form label-position="top">
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="公司"><el-input v-model="exp.company" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="职位"><el-input v-model="exp.position" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="在职时间">
          <el-date-picker v-model="exp.dateRange" type="monthrange" range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份" value-format="YYYY-MM" />
        </el-form-item>
        
        <div class="description-wrapper">
            <div class="description-label">
                <span>工作内容</span>
                <el-button 
                    class="ai-polish-button"
                    @click="handlePolish(exp)"
                    :loading="exp.isPolishing"
                >
                    <el-icon class="magic-icon"><MagicStick /></el-icon>
                    AI 润色
                </el-button>
            </div>
            <RichTextEditor v-model="exp.description" />
        </div>
      </el-form>
      <el-button link type="danger" @click="removeItem('experiences', index)" style="margin-top: 10px;">删除此条经历</el-button>
    </div>
    <el-button plain type="primary" @click="addItem('experiences')">添加工作经历</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import RichTextEditor from '@/components/common/RichTextEditor.vue';
import { MagicStick } from '@element-plus/icons-vue';
import { polishDescriptionApi } from '@/api/modules/resumeEditor';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';

const { module, propKey } = defineProps<{ module: any; propKey: string }>();
const props = computed(() => module.props);
const editorStore = useResumeEditorStore();

const newItemTemplates: Record<string, object> = {
  experiences: { company: '', position: '', dateRange: [], description: '<p><br></p>', isPolishing: false },
};

const handlePolish = async (experience: any) => {
  experience.isPolishing = true;
  try {
    const jobPosition = editorStore.resumeMeta?.job_title;
    const res = await polishDescriptionApi(experience.description, jobPosition);
    experience.description = res.polished_html;
  } finally {
    experience.isPolishing = false;
  }
};

const addItem = (key: string) => {
  if (props.value[key]) {
    (props.value[key] as any[]).push({ id: uuidv4(), ...newItemTemplates[key] });
  }
};
const removeItem = (key: string, index: number) => {
  if (props.value[key]) {
    (props.value[key] as any[]).splice(index, 1);
  }
};
</script>

<style scoped>
.list-item-form-vertical { padding: 15px; border: 1px solid #f0f0f0; margin-bottom: 15px; border-radius: 4px; }
.description-wrapper { width: 100%; margin-top: 10px; }
.description-label {
  display: flex;
  justify-content: space-between;
  width: 100%;
  align-items: center;
  margin-bottom: 8px;
}
</style>

<!-- 【核心修复】添加全局或共享样式来美化按钮 -->
<style>
.ai-polish-button {
  padding: 5px 10px;
  height: auto;
  font-size: 12px;
  border-radius: 15px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  transition: all 0.3s ease;
  box-shadow: 0 2px 5px rgba(118, 75, 162, 0.3);
}

.ai-polish-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(118, 75, 162, 0.4);
}

.ai-polish-button .magic-icon {
  margin-right: 4px;
  animation: sparkle 1.5s infinite;
}

@keyframes sparkle {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
}
</style>