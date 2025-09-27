<template>
  <SectionCard title="基本信息">
    <el-form label-position="top">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="姓名">
            <el-input v-model="store.resumeData.full_name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="期望职位">
            <el-input v-model="store.resumeData.job_title" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="联系电话">
            <el-input v-model="store.resumeData.phone" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="电子邮箱">
            <el-input v-model="store.resumeData.email" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="所在城市">
            <el-input v-model="store.resumeData.city" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
           <el-form-item label="个人总结">
            <el-input v-model="store.resumeData.summary" type="textarea" :rows="4" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from '@/components/common/SectionCard.vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';

const store = useResumeEditorStore();
</script>