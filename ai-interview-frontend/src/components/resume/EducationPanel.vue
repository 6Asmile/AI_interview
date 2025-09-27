<template>
  <SectionCard title="教育背景">
    <div v-for="(edu, index) in store.resumeData.educations" :key="index" class="form-block">
      <el-form label-position="top">
         <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="学校名称">
                <el-input v-model="edu.school" />
              </el-form-item>
            </el-col>
             <el-col :span="12">
              <el-form-item label="专业">
                <el-input v-model="edu.major" />
              </el-form-item>
            </el-col>
             <el-col :span="12">
              <el-form-item label="学位">
                <el-input v-model="edu.degree" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
               <el-form-item label="起止日期">
                <el-date-picker
                  v-model="edu.start_date"
                  type="month"
                  placeholder="开始月份"
                  style="width: 48%;"
                  value-format="YYYY-MM-DD"
                />
                <span style="margin: 0 4px;">-</span>
                <el-date-picker
                  v-model="edu.end_date"
                  type="month"
                  placeholder="结束月份"
                  style="width: 48%;"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
         </el-row>
      </el-form>
      <el-button type="danger" link class="delete-btn" @click="store.removeEducation(index)">删除此条</el-button>
    </div>
     <el-button type="primary" link @click="store.addEducation">+ 添加教育经历</el-button>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from '@/components/common/SectionCard.vue';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';

const store = useResumeEditorStore();
</script>

<style scoped>
.form-block {
  padding: 10px;
  border: 1px solid #eee;
  border-radius: 4px;
  margin-bottom: 15px;
  position: relative;
}
.delete-btn {
  position: absolute;
  top: 5px;
  right: 10px;
}
</style>