<template>
  <el-card>
    <template #header>
      <div class="section-header">
        <h3>教育背景</h3>
        <el-button type="primary" :icon="Plus" circle @click="addNewEducation" />
      </div>
    </template>
    <div class="section-content">
      <el-empty v-if="educations.length === 0" description="暂无教育经历，请点击右上角添加" />
      <el-form v-for="(edu, index) in educations" :key="edu.localId || edu.id" :model="edu" label-width="80px" class="form-item">
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="学校"><el-input v-model="edu.school" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="学位"><el-input v-model="edu.degree" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="专业"><el-input v-model="edu.major" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="时间">
            <el-date-picker v-model="edu.dateRange" type="monthrange" range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
        </el-row>
        <div class="item-controls">
          <el-button type="primary" plain @click="saveEducation(edu)">保存</el-button>
          <el-button type="danger" plain @click="deleteEducation(edu, index)">删除</el-button>
        </div>
      </el-form>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { Plus } from '@element-plus/icons-vue';
import { educationApi, type EducationItem } from '@/api/modules/resumeEditor';
import { ElMessage, ElMessageBox } from 'element-plus';

const props = defineProps<{ resumeId: number; initialData: EducationItem[]; }>();
const emit = defineEmits(['change']); // 定义 change 事件

const educations = ref<any[]>([]);
watch(() => props.initialData, (newData) => {
  educations.value = (newData || []).map(item => ({...item, dateRange: [item.start_date, item.end_date] }));
}, { immediate: true, deep: true });

const addNewEducation = () => {
  educations.value.unshift({ school: '', degree: '', major: '', dateRange: [], localId: Date.now() });
};

const saveEducation = async (eduItem: any) => {
  const [start_date, end_date] = eduItem.dateRange || [null, null];
  if (!start_date || !end_date) { ElMessage.warning("请选择完整的起止日期"); return; }
  const dataToSave = { school: eduItem.school, degree: eduItem.degree, major: eduItem.major, start_date, end_date };

  try {
    if (eduItem.id) {
      await educationApi.update(props.resumeId, eduItem.id, dataToSave);
    } else {
      await educationApi.create(props.resumeId, dataToSave);
    }
    ElMessage.success('保存成功！');
    emit('change'); // 保存成功后，通知父组件刷新数据
  } catch (error) { ElMessage.error('保存失败'); }
};

const deleteEducation = async (eduItem: any, index: number) => {
  if (!eduItem.id) { educations.value.splice(index, 1); return; }
  await ElMessageBox.confirm('确定要删除这条教育经历吗？', '警告', { type: 'warning' });
  try {
    await educationApi.destroy(props.resumeId, eduItem.id);
    ElMessage.success('删除成功！');
    emit('change'); // 删除成功后，通知父组件刷新数据
  } catch (error) { ElMessage.error('删除失败'); }
};
</script>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: center; }
h3 { margin: 0; }
.form-item { padding: 20px; border-bottom: 1px dashed #e4e7ed; }
.form-item:last-child { border-bottom: none; }
.item-controls { text-align: right; margin-top: 10px; }
</style>