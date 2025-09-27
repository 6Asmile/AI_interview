<template>
  <el-collapse-item name="2" title="教育背景">
    <div v-for="(edu, index) in model" :key="index" class="panel-item">
      <el-form :model="edu" label-position="top">
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="学校名称"><el-input v-model="edu.school" placeholder="如：XX大学" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="学位"><el-input v-model="edu.degree" placeholder="如：本科" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="专业"><el-input v-model="edu.major" placeholder="如：计算机科学与技术" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="在校时间">
            <el-date-picker v-model="edu.dateRange" type="monthrange" range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份" value-format="YYYY-MM-DD" style="width: 100%;" />
          </el-form-item></el-col>
        </el-row>
      </el-form>
      <div class="item-controls">
        <el-button type="danger" @click="removeItem(index)" circle plain><el-icon><Delete /></el-icon></el-button>
      </div>
    </div>
    <el-button @click="addItem" style="width: 100%; margin-top: 10px;">+ 添加教育经历</el-button>
  </el-collapse-item>
</template>

<script setup lang="ts">
import { Delete } from '@element-plus/icons-vue';
const model = defineModel<any[]>({ required: true });

const addItem = () => {
  if (model.value) {
    model.value.unshift({ school: '', degree: '', major: '', dateRange: [] });
  }
};

const removeItem = (index: number) => {
  if (model.value) {
    model.value.splice(index, 1);
  }
};
</script>

<style scoped>
.panel-item { position: relative; padding: 20px 15px 10px; border-bottom: 1px dashed #dcdfe6; }
.panel-item:last-of-type { border-bottom: none; }
.item-controls { position: absolute; top: 10px; right: 0px; }
</style>