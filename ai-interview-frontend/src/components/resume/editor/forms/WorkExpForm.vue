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
          <el-date-picker
            v-model="exp.dateRange"
            type="monthrange"
            range-separator="至"
            start-placeholder="开始月份"
            end-placeholder="结束月份"
            value-format="YYYY-MM"
          />
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
      <el-button link type="danger" @click="removeItem(index)" style="margin-top: 10px;">删除此条经历</el-button>
    </div>
    <el-button plain type="primary" @click="addItem">添加工作经历</el-button>
    
    <el-dialog v-model="diffDialogVisible" title="AI 润色建议" width="60%">
      <DiffViewer v-if="diffData" :old-text="diffData.oldHtml" :new-text="diffData.newHtml" />
      <template #footer>
        <el-button @click="diffDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="applyPolish">采纳修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import RichTextEditor from '@/components/common/RichTextEditor.vue';
import { MagicStick } from '@element-plus/icons-vue';
import { polishDescriptionApi } from '@/api/modules/resumeEditor';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import DiffViewer from '@/components/common/DiffViewer.vue';

// 移除了未使用的 propKey
const { module } = defineProps<{ module: any }>();
const props = computed(() => module.props);
const editorStore = useResumeEditorStore();

const diffDialogVisible = ref(false);
const diffData = ref<{ oldHtml: string; newHtml: string; target: any } | null>(null);

const newItemTemplates: Record<string, object> = {
  experiences: { company: '', position: '', dateRange: [], description: '<p><br></p>', isPolishing: false },
};

const handlePolish = async (experience: any) => {
  experience.isPolishing = true;
  try {
    const jobPosition = editorStore.resumeMeta?.job_title;
    const oldHtml = experience.description;
    const res = await polishDescriptionApi(oldHtml, jobPosition);
    diffData.value = { oldHtml, newHtml: res.polished_html, target: experience };
    diffDialogVisible.value = true;
  } finally {
    experience.isPolishing = false;
  }
};

const applyPolish = () => {
  if (diffData.value) {
    diffData.value.target.description = diffData.value.newHtml;
    diffDialogVisible.value = false;
    diffData.value = null;
  }
};

const addItem = () => {
  if (props.value.experiences) {
    (props.value.experiences as any[]).push({ id: uuidv4(), ...newItemTemplates.experiences });
  }
};

const removeItem = (index: number) => {
  if (props.value.experiences) {
    (props.value.experiences as any[]).splice(index, 1);
  }
};
</script>

<style scoped>
.list-item-form-vertical { 
  padding: 15px; 
  border: 1px solid #f0f0f0; 
  margin-bottom: 15px; 
  border-radius: 4px; 
}
.description-wrapper { 
  width: 100%; 
  margin-top: 10px; 
}
.description-label {
  display: flex;
  justify-content: space-between;
  width: 100%;
  align-items: center;
  margin-bottom: 8px;
}
</style>

<style>
/* 全局样式保持不变，用于美化按钮 */
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