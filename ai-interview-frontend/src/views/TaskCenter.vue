<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { cancelTaskApi, getTasksApi, retryTaskApi, type AsyncTaskItem, type AsyncTaskStatus } from '@/api/modules/task';
import { formatDateTime } from '@/utils/format';

const loading = ref(false);
const status = ref('');
const tasks = ref<AsyncTaskItem[]>([]);
let timer: number | undefined;
const statusLabels: Record<AsyncTaskStatus, string> = {
  pending: '排队中', running: '处理中', review_required: '待确认',
  succeeded: '已完成', failed: '失败', canceled: '已取消',
};
const statusType = (value: AsyncTaskStatus) => ({
  pending: 'info', running: 'primary', review_required: 'warning',
  succeeded: 'success', failed: 'danger', canceled: 'info',
}[value] as any);
const activeCount = computed(() => tasks.value.filter(item => ['pending', 'running'].includes(item.status)).length);

const load = async (silent = false) => {
  if (!silent) loading.value = true;
  try {
    const response = await getTasksApi(status.value ? { status: status.value } : undefined);
    tasks.value = response.results || [];
  } finally { if (!silent) loading.value = false; }
};
const retry = async (item: AsyncTaskItem) => {
  await retryTaskApi(item.id);
  ElMessage.success('任务已重新进入队列。');
  await load(true);
};
const cancel = async (item: AsyncTaskItem) => {
  await ElMessageBox.confirm('确认取消该任务？已完成的解析结果不会被伪造或补齐。', '取消任务', { type: 'warning' });
  await cancelTaskApi(item.id);
  ElMessage.success('任务已取消。');
  await load(true);
};
onMounted(() => { load(); timer = window.setInterval(() => load(true), 10000); });
onUnmounted(() => timer && window.clearInterval(timer));
</script>

<template>
  <div class="task-page" v-loading="loading">
    <header class="task-header">
      <div><h1>任务中心</h1><p>查看简历解析、知识库索引、报告生成和媒体处理的真实运行状态。</p></div>
      <el-tag v-if="activeCount" type="primary">{{ activeCount }} 个任务处理中</el-tag>
    </header>
    <div class="task-toolbar">
      <el-select v-model="status" placeholder="全部状态" clearable @change="load()">
        <el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" />
      </el-select>
      <el-button @click="load()">刷新</el-button>
    </div>
    <el-empty v-if="!tasks.length" description="暂无异步任务" />
    <div v-else class="task-list">
      <article v-for="item in tasks" :key="item.id" class="task-row">
        <div class="task-main">
          <div class="task-title"><strong>{{ item.title }}</strong><el-tag size="small" :type="statusType(item.status)">{{ statusLabels[item.status] }}</el-tag></div>
          <el-progress v-if="['pending', 'running'].includes(item.status)" :percentage="item.progress" :stroke-width="8" />
          <p v-if="item.error_message" class="task-error">{{ item.error_message }}</p>
          <small>创建于 {{ formatDateTime(item.created_at) }}<template v-if="item.completed_at"> · 完成于 {{ formatDateTime(item.completed_at) }}</template></small>
        </div>
        <div class="task-actions">
          <el-button v-if="item.can_retry" type="primary" plain @click="retry(item)">重试</el-button>
          <el-button v-if="item.can_cancel" type="danger" plain @click="cancel(item)">取消</el-button>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.task-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }
.task-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }
.task-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }
.task-header p { margin: 8px 0 0; color: #667085; }
.task-toolbar { display: flex; gap: 10px; margin: 20px 0; }
.task-toolbar .el-select { width: 180px; }
.task-list { border: 1px solid #e1e6ee; border-radius: 8px; background: #fff; }
.task-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 18px 20px; border-bottom: 1px solid #edf0f4; }
.task-row:last-child { border-bottom: 0; }
.task-main { min-width: 0; flex: 1; }
.task-title { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.task-title strong { overflow-wrap: anywhere; }
.task-main small { color: #667085; }
.task-error { margin: 8px 0; color: #b42318; }
.task-actions { display: flex; flex: 0 0 auto; }
@media (max-width: 600px) { .task-page { padding: 14px; } .task-header, .task-row { align-items: flex-start; flex-direction: column; } .task-actions { width: 100%; } }
</style>
