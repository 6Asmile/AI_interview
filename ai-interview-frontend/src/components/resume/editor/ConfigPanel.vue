<!-- src/components/resume/editor/ConfigPanel.vue -->
<template>
  <div class="config-panel">
    <div v-if="selectedComponent" class="panel-content">
      <h3 class="panel-title">编辑 {{ selectedComponent.title }}</h3>
      
      <el-tabs v-model="activeTab" class="config-tabs">
        <!-- 内容配置 -->
        <el-tab-pane label="内容" name="props">
          <el-form label-position="top">
            <!-- 【修复】使用 key in editableProps 遍历，类型更安全 -->
            <template v-for="key in Object.keys(editableProps)" :key="key">
              
              <!-- 通用标题编辑器 -->
              <el-form-item v-if="key === 'title'" :label="propLabels[key] || '模块标题'">
                <el-input v-model="editableProps[key]" @input="updateProps" />
              </el-form-item>

              <!-- 通用文本/文本域编辑器 -->
              <el-form-item v-if="typeof editableProps[key] === 'string' && !['title', 'photo'].includes(key)" :label="propLabels[key] || key">
                <el-input type="textarea" autosize v-model="editableProps[key]" @input="updateProps" />
              </el-form-item>
              
              <!-- 动态列表编辑器 -->
              <div v-if="Array.isArray(editableProps[key])">
                <el-form-item :label="propLabels[key] || '列表项'"></el-form-item>
                <!-- 【修复】直接使用 editableProps[key] 作为 v-model -->
                <div v-for="(item, index) in editableProps[key]" :key="item.id" class="list-item">
                  <!-- 【修复】使用 key in item 遍历，并移除未使用的 fieldValue -->
                  <template v-for="fieldKey in Object.keys(item)" :key="fieldKey">
                    <el-input 
                      v-if="fieldKey !== 'id'"
                      :placeholder="getPlaceholder(String(fieldKey))"
                      v-model="item[fieldKey]"
                      :autosize="{ minRows: 2, maxRows: 6 }"
                      :type="fieldKey === 'description' ? 'textarea' : 'text'"
                      @input="updateProps"
                    />
                  </template>
                  <el-button type="danger" plain size="small" @click="removeItem(key, index)">删除此条</el-button>
                </div>
                <el-button type="primary" plain @click="addItem(key)">添加一项</el-button>
              </div>

            </template>
          </el-form>
        </el-tab-pane>

        <!-- 样式配置 -->
        <el-tab-pane label="样式" name="styles">
           <el-form label-position="top">
             <!-- 【修复】使用 key in editableStyles 遍历 -->
             <el-form-item v-for="key in Object.keys(editableStyles)" :key="key" :label="styleLabels[key] || key">
              <el-input v-model="editableStyles[key]" @input="updateStyles" />
             </el-form-item>
           </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
    <div v-else class="empty-tip">
      <el-empty description="在画布中选择一个组件进行配置" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';

const editorStore = useResumeEditorStore();
const selectedComponent = computed(() => editorStore.selectedComponent);

const activeTab = ref('props');
const editableProps = ref<Record<string, any>>({});
const editableStyles = ref<Record<string, any>>({});

// --- 映射与模板 (保持不变) ---
const propLabels: Record<string, string> = { name: '姓名', jobTitle: '求职岗位', phone: '电话', email: '邮箱', summary: '总结内容', title: '模块标题', items: '信息条目', educations: '教育经历', experiences: '工作经历', projects: '项目经历', skills: '专业技能' };
const styleLabels: Record<string, string> = { padding: '内边距', borderBottom: '下边框' };
const placeholders: Record<string, string> = { name: '技能名称/项目名称', school: '学校名称', company: '公司名称', proficiency: '熟练度', role: '担任角色', position: '职位', major: '专业', degree: '学位', dateRange: '时间范围', description: '详细描述', label: '标签', value: '内容', techStack: '技术栈', projectUrl: '项目链接' };
const newItemTemplates: Record<string, object> = {
    items: { icon: 'Star', label: '新条目', value: '新内容' },
    educations: { school: '学校名称', major: '专业', degree: '学位', dateRange: '时间', description: '' },
    experiences: { company: '公司名称', position: '职位', dateRange: '时间', description: '' },
    projects: { name: '项目名称', role: '角色', dateRange: '时间', techStack: '', description: '', projectUrl: '' },
    skills: { name: '技能名称', proficiency: '熟练度' },
};

const getPlaceholder = (key: string) => placeholders[key] || key;

watch(selectedComponent, (newVal) => {
  if (newVal) {
    editableProps.value = JSON.parse(JSON.stringify(newVal.props));
    editableStyles.value = JSON.parse(JSON.stringify(newVal.styles));
  } else {
    // 当没有选中组件时，清空表单
    editableProps.value = {};
    editableStyles.value = {};
  }
}, { deep: true, immediate: true });

const updateProps = () => editorStore.updateSelectedComponentProps(editableProps.value);
const updateStyles = () => editorStore.updateSelectedComponentStyles(editableStyles.value);

const addItem = (key: string) => {
  if (editableProps.value[key] && newItemTemplates[key]) {
    editableProps.value[key].push({ id: uuidv4(), ...newItemTemplates[key] });
    updateProps();
  }
};
const removeItem = (key: string, index: number) => {
  if (editableProps.value[key]) {
    editableProps.value[key].splice(index, 1);
    updateProps();
  }
};
</script>

<style scoped>
/* 样式与之前保持一致，无需修改 */
.panel-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.config-tabs { border: none; }
.empty-tip { padding-top: 50px; }
.list-item { padding: 12px; border: 1px solid #eee; border-radius: 4px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px; }
</style>