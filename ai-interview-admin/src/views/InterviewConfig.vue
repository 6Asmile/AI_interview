<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { api } from '@/api';

const active = ref('templates');
const loading = ref(false);
const rows = reactive<Record<string, any[]>>({ templates: [], rubrics: [], datasets: [], runs: [] });
const dialog = ref(false);
const form = reactive<any>({ name: '', description: '', visibility: 'shared', rubric_id: null, interview_mode: 'project_with_fundamentals', target_duration_minutes: 30, dataset_id: null, template_id: null, operation_reason: '' });

const load = async (resource = active.value) => {
  loading.value = true;
  try { rows[resource] = await api.get(`/interview-config/${resource}/`); }
  finally { loading.value = false; }
};
const switchTab = async (name: any) => { await load(name.props.name); };
const openCreate = () => { Object.assign(form, { name: '', description: '', visibility: 'shared', rubric_id: null, interview_mode: 'project_with_fundamentals', target_duration_minutes: 30, dataset_id: null, template_id: null, operation_reason: '' }); dialog.value = true; };
const create = async () => { await api.post(`/interview-config/${active.value}/`, form, { headers: { 'Idempotency-Key': crypto.randomUUID() } }); dialog.value = false; ElMessage.success(active.value==='runs'?'评估运行已进入队列。':'配置已创建。'); await load(); };
onMounted(async()=>{ await Promise.all(['templates','rubrics','datasets','runs'].map(load)); });
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="page-header"><div><h1>模板、量表与评估</h1><p>统一管理面试结构、评分标准和真实匿名化离线评估运行。</p></div><el-button type="primary" @click="openCreate">{{active==='runs'?'运行评估':'新建配置'}}</el-button></header>
    <el-tabs v-model="active" class="config-tabs" @tab-click="switchTab">
      <el-tab-pane label="面试模板" name="templates"><div class="data-surface"><el-table :data="rows.templates"><el-table-column prop="name" label="模板" min-width="180" /><el-table-column prop="interview_mode" label="模式" min-width="180" /><el-table-column prop="rubric_name" label="评分量表" min-width="160" /><el-table-column prop="target_duration_minutes" label="目标时长" width="100" /><el-table-column prop="stage_count" label="阶段" width="80" /><el-table-column prop="version" label="版本" width="80" /><el-table-column label="状态" width="90"><template #default="{row}"><el-tag :type="row.is_active?'success':'info'">{{row.is_active?'启用':'停用'}}</el-tag></template></el-table-column></el-table></div></el-tab-pane>
      <el-tab-pane label="评分量表" name="rubrics"><div class="data-surface"><el-table :data="rows.rubrics"><el-table-column prop="name" label="量表" min-width="200" /><el-table-column prop="description" label="说明" min-width="260" show-overflow-tooltip /><el-table-column prop="dimension_count" label="维度" width="90" /><el-table-column prop="version" label="版本" width="90" /><el-table-column prop="visibility" label="范围" width="100" /></el-table></div></el-tab-pane>
      <el-tab-pane label="评估数据集" name="datasets"><div class="data-surface"><el-table :data="rows.datasets"><el-table-column prop="name" label="数据集" min-width="220" /><el-table-column prop="description" label="说明" min-width="260" /><el-table-column prop="case_count" label="真实样例" width="100" /><el-table-column prop="visibility" label="范围" width="100" /></el-table></div></el-tab-pane>
      <el-tab-pane label="评估运行" name="runs"><div class="data-surface"><el-table :data="rows.runs"><el-table-column prop="dataset" label="数据集" min-width="180" /><el-table-column prop="template" label="模板" min-width="160" /><el-table-column prop="status" label="状态" width="110" /><el-table-column prop="metric_count" label="指标" width="80" /><el-table-column prop="error_message" label="错误" min-width="220" show-overflow-tooltip /><el-table-column prop="created_at" label="创建时间" min-width="170" /></el-table></div></el-tab-pane>
    </el-tabs>
    <el-dialog v-model="dialog" :title="active==='runs'?'运行离线评估':'新建面试配置'" width="560px"><el-form label-position="top">
      <template v-if="active!=='runs'"><el-form-item label="名称"><el-input v-model="form.name" /></el-form-item><el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item><el-form-item label="范围"><el-radio-group v-model="form.visibility"><el-radio-button value="shared">共享</el-radio-button><el-radio-button value="private">私有</el-radio-button></el-radio-group></el-form-item></template>
      <template v-if="active==='templates'"><el-form-item label="评分量表"><el-select v-model="form.rubric_id" style="width:100%"><el-option v-for="item in rows.rubrics" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="面试模式"><el-select v-model="form.interview_mode" style="width:100%"><el-option label="项目穿插基础知识" value="project_with_fundamentals" /><el-option label="严格追问" value="strict" /><el-option label="宽松交流" value="relaxed" /><el-option label="系统设计" value="system_design" /></el-select></el-form-item><el-form-item label="目标时长"><el-input-number v-model="form.target_duration_minutes" :min="10" :max="90" /></el-form-item></template>
      <template v-if="active==='runs'"><el-form-item label="数据集"><el-select v-model="form.dataset_id" style="width:100%"><el-option v-for="item in rows.datasets" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="模板（可选）"><el-select v-model="form.template_id" clearable style="width:100%"><el-option v-for="item in rows.templates" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></template>
      <el-form-item label="操作原因"><el-input v-model="form.operation_reason" type="textarea" /></el-form-item>
    </el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :disabled="!form.operation_reason.trim()||(active!=='runs'&&!form.name)||(active==='templates'&&!form.rubric_id)||(active==='runs'&&!form.dataset_id)" @click="create">确认</el-button></template></el-dialog>
  </div>
</template>

<style scoped>.config-tabs{margin-top:18px}</style>
