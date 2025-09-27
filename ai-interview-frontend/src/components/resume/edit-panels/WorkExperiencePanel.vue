<template>
  <el-collapse-item name="3" title="工作经历">
    <div v-for="(exp, index) in model" :key="index" class="panel-item">
      <el-form :model="exp" label-position="top">
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="公司名称"><el-input v-model="exp.company" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="职位"><el-input v-model="exp.position" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="工作时间">
            <el-date-picker v-model="exp.dateRange" type="monthrange" range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="24"><el-form-item label="工作描述">
            <el-input v-model="exp.description" type="textarea" :rows="4" placeholder="请详细描述您的工作内容、职责和主要成就..." />
          </el-form-item></el-col>
        </el-row>
      </el-form>
      <div class="item-controls">
        <el-button type="danger" @click="removeItem(index)" circle plain><el-icon><Delete /></el-icon></el-button>
      </div>
    </div>
    <el-button @click="addItem" style="width: 100%; margin-top: 10px;">+ 添加工作经历</el-button>
  </el-collapse-item>
</template>

<script setup lang="ts">
import { Delete } from '@element-plus/icons-vue';

// 使用 defineModel 来实现与父组件的双向绑定
const model = defineModel<any[]>({ required: true });

const addItem = () => {
  if (model.value) {
    model.value.unshift({ company: '', position: '', dateRange: [], description: '' });
  }
};

const removeItem = (index: number) => {
  if (model.value) {
    model.value.splice(index, 1);
  }
};
</script>

<style scoped>
.panel-item {
  position: relative;
  padding: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 15px;
}
.item-controls {
  position: absolute;
  top: 15px;
  right: 15px;
}
</style>