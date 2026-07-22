<script setup lang="ts">
import { onMounted, ref } from 'vue'; import { ElMessage, ElMessageBox } from 'element-plus'; import { api } from '@/api';
const loading=ref(false); const rows=ref<any[]>([]);
const load=async()=>{loading.value=true;try{rows.value=await api.get('/moderation/reports/')}finally{loading.value=false}};
const decide=async(row:any,decision:'resolve'|'reject')=>{const result=await ElMessageBox.prompt('填写处理依据，该内容会进入不可修改的审计日志。','处理举报',{inputValidator:value=>Boolean(value?.trim())||'必须填写操作原因'});await api.post(`/moderation/reports/${row.id}/${decision}/`,{operation_reason:result.value.trim()},{headers:{'Idempotency-Key':crypto.randomUUID()}});ElMessage.success('举报状态已更新。');await load()};
onMounted(load);
</script>
<template><div class="page" v-loading="loading"><header class="page-header"><div><h1>社区与私信审核</h1><p>处理用户真实举报；默认不主动浏览私人对话。</p></div><el-button @click="load">刷新</el-button></header><div class="data-surface" style="margin-top:18px"><el-table :data="rows"><el-table-column prop="reason" label="举报类型" min-width="150" /><el-table-column prop="detail" label="说明" min-width="220" show-overflow-tooltip /><el-table-column prop="reporter" label="举报人" min-width="180" /><el-table-column prop="sender" label="被举报人" min-width="180" /><el-table-column prop="status" label="状态" width="100" /><el-table-column label="操作" width="150"><template #default="{row}"><el-button link type="primary" @click="decide(row,'resolve')">处理</el-button><el-button link @click="decide(row,'reject')">驳回</el-button></template></el-table-column></el-table></div></div></template>
