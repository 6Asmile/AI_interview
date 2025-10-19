<!-- src/components/resume/editor/forms/GenericListForm.vue -->
<template>
  <div>
    <div v-for="(item, index) in items" :key="item.id" class="list-item-form-vertical">
      <el-form label-position="top">
        <template v-for="key in Object.keys(item)" :key="key">
          <el-form-item :label="getLabel(key)" v-if="key !== 'id' && key !== 'isPolishing'">
            <el-date-picker
              v-if="key === 'dateRange'"
              v-model="item[key]"
              type="monthrange"
              range-separator="至"
              start-placeholder="开始月份"
              end-placeholder="结束月份"
              value-format="YYYY-MM"
              style="width: 100%;"
            />
            <div v-else-if="key === 'description'" class="description-wrapper">
                <div class="description-label">
                    <span>详细描述</span>
                    <el-button 
                        class="ai-polish-button"
                        @click="handlePolish(item)"
                        :loading="item.isPolishing"
                    >
                        <el-icon class="magic-icon"><MagicStick /></el-icon>
                        AI 润色
                    </el-button>
                </div>
                <RichTextEditor v-model="item.description" />
            </div>
            <el-input 
              v-else
              :type="getInputType(key)" 
              autosize 
              v-model="item[key]"
              :placeholder="getLabel(key)"
            />
          </el-form-item>
        </template>
      </el-form>
      <el-button link type="danger" @click="removeItem(index)">删除此条</el-button>
    </div>
    <el-button plain type="primary" @click="addItem">添加一项</el-button>

    <!-- Diff 对话框 -->
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
import { allTemplates } from '@/resume-templates/template-definitions';
import RichTextEditor from '@/components/common/RichTextEditor.vue';
import DiffViewer from '@/components/common/DiffViewer.vue';
import { MagicStick } from '@element-plus/icons-vue';
import { polishDescriptionApi } from '@/api/modules/resumeEditor';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';

const { module, propKey } = defineProps<{ module: any; propKey: string }>();

const items = computed(() => module.props[propKey]);
const editorStore = useResumeEditorStore();

const diffDialogVisible = ref(false);
const diffData = ref<{ oldHtml: string; newHtml: string; target: any } | null>(null);

const labels: Record<string, string> = { name: '名称', school: '学校', company: '公司', proficiency: '熟练度', role: '角色', position: '职位', major: '专业', degree: '学位', dateRange: '时间范围', subtitle: '副标题/分数', description: '详细描述', techStack: '技术栈', content: '内容', title: '标题' };
const getInputType = (key: string) => (key === 'description' || key === 'content' ? 'textarea' : 'text');
const getLabel = (key: string) => labels[key] || key;

const handlePolish = async (item: any) => {
  item.isPolishing = true;
  try {
    const jobPosition = editorStore.resumeMeta?.job_title;
    const oldHtml = item.description;
    const res = await polishDescriptionApi(oldHtml, jobPosition);
    diffData.value = { oldHtml, newHtml: res.polished_html, target: item };
    diffDialogVisible.value = true;
  } finally {
    item.isPolishing = false;
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
  if (items.value) {
    const template = allTemplates.find(t => t.moduleType === module.moduleType);
    if (!template) return;
    const newItemTemplate = (template.props[propKey] as any[])?.[0];
    if (!newItemTemplate) return;
    const newItem = { ...newItemTemplate, id: uuidv4(), isPolishing: false };
    items.value.push(newItem);
  }
};

const removeItem = (index: number) => {
  if (items.value) {
    items.value.splice(index, 1);
  }
};
</script>

<style scoped>
.list-item-form-vertical { padding: 15px; border: 1px solid #f0f0f0; margin-bottom: 15px; border-radius: 4px; }
.description-wrapper { width: 100%; }
.description-label { display: flex; justify-content: space-between; width: 100%; align-items: center; margin-bottom: 8px; }
</style>