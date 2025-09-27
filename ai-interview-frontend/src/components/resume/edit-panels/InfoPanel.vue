<template>
  <el-collapse-item name="1" title="基本资料">
    <el-form :model="model" label-position="top">
      <el-row :gutter="20">
        <el-col :span="12"><el-form-item label="姓名"><el-input v-model="model.full_name" placeholder="您的姓名" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="期望职位"><el-input v-model="model.job_title" placeholder="如：软件工程师" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="电话"><el-input v-model="model.phone" placeholder="您的联系电话" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="邮箱"><el-input v-model="model.email" placeholder="您的联系邮箱" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="城市"><el-input v-model="model.city" placeholder="如：上海" /></el-form-item></el-col>
        <el-col :span="24"><el-form-item label="个人总结"><el-input v-model="model.summary" type="textarea" :rows="3" placeholder="一句话总结您的优势" /></el-form-item></el-col>
      </el-row>
    </el-form>
  </el-collapse-item>
</template>

<script setup lang="ts">
const model = defineModel<any>({ required: true });
</script>