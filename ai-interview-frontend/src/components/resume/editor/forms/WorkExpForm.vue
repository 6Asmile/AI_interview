<!-- src/components/resume/editor/forms/WorkExpForm.vue -->
<template>
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
      
      <!-- 【核心修改】将 el-input 替换为 RichTextEditor -->
      <el-form-item label="工作内容">
        <RichTextEditor v-model="exp.description" />
      </el-form-item>

    </el-form>
    <el-button link type="danger" @click="removeItem('experiences', index)" style="margin-top: 10px;">删除此条经历</el-button>
  </div>
  <el-button plain type="primary" @click="addItem('experiences')">添加工作经历</el-button>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { v4 as uuidv4 } from 'uuid';
// 【核心修改】导入 RichTextEditor
import RichTextEditor from '@/components/common/RichTextEditor.vue';

const { module, propKey } = defineProps<{ module: any; propKey: string }>();
const props = computed(() => module.props);

const newItemTemplates: Record<string, object> = {
  experiences: { company: '', position: '', dateRange: [], description: '<p><br></p>' }, // 默认值改为空段落
};

const addItem = (propKey: string) => {
  if (props.value[propKey]) {
    (props.value[propKey] as any[]).push({ id: uuidv4(), ...newItemTemplates[propKey] });
  }
};
const removeItem = (propKey: string, index: number) => {
  if (props.value[propKey]) {
    (props.value[propKey] as any[]).splice(index, 1);
  }
};
</script>

<style scoped>
.list-item-form-vertical { padding: 15px; border: 1px solid #f0f0f0; margin-bottom: 15px; border-radius: 4px; }
</style>