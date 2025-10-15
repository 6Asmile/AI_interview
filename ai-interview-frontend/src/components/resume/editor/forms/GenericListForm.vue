<!-- src/components/resume/editor/forms/GenericListForm.vue -->
<template>
  <div>
    <div v-for="(item, index) in items" :key="item.id" class="list-item-form-vertical">
      <el-form label-position="top">
        <template v-for="key in Object.keys(item)" :key="key">
          <el-form-item :label="getLabel(key)" v-if="key !== 'id'">
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import { allTemplates } from '@/resume-templates/template-definitions';

const { module, propKey } = defineProps<{ module: any; propKey: string }>();

const items = computed(() => module.props[propKey]);

const labels: Record<string, string> = { name: '名称', school: '学校', company: '公司', proficiency: '熟练度', role: '角色', position: '职位', major: '专业', degree: '学位', dateRange: '时间范围', subtitle: '副标题/分数', description: '详细描述', techStack: '技术栈', content: '内容', title: '标题' };
const getInputType = (key: string) => (key === 'description' || key === 'content' ? 'textarea' : 'text');
const getLabel = (key: string) => labels[key] || key;

const addItem = () => {
  if (items.value) {
    const template = allTemplates.find(t => t.moduleType === module.moduleType);
    if (!template) return;
    const newItemTemplate = (template.props[propKey] as any[])?.[0];
    if (!newItemTemplate) return;
    const newItem = { ...newItemTemplate, id: uuidv4() };
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
</style>