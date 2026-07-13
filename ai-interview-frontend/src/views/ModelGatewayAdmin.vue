<template>
  <div class="gateway-page">
    <header class="page-header">
      <div><h1>模型网关</h1><p>管理任务别名、部署、平台凭据和脱敏调用账本。</p></div>
      <el-button v-if="activeTab === 'deployments'" type="primary" :icon="Plus" @click="openDeployment">新增部署</el-button>
      <el-button v-else-if="activeTab === 'credentials'" type="primary" :icon="Key" @click="credentialDialog = true">新增凭据</el-button>
    </header>

    <el-tabs v-model="activeTab" class="gateway-tabs">
      <el-tab-pane label="任务路由" name="aliases">
        <el-table :data="aliases" v-loading="loading">
          <el-table-column prop="slug" label="任务别名" min-width="220" />
          <el-table-column prop="name" label="用途" min-width="180" />
          <el-table-column prop="model_type" label="类型" width="120" />
          <el-table-column label="部署链" min-width="360">
            <template #default="{ row }">
              <el-tag v-for="target in row.route_policy?.targets || []" :key="target.deployment_detail.id" class="route-tag" :type="target.deployment_detail.last_health_status === 'degraded' ? 'danger' : 'info'">
                {{ target.order + 1 }}. {{ target.deployment_detail.name }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="模型部署" name="deployments">
        <el-table :data="deployments" v-loading="loading">
          <el-table-column prop="name" label="部署名称" min-width="190" />
          <el-table-column prop="provider" label="Provider" width="140" />
          <el-table-column prop="remote_model" label="远端模型" min-width="200" />
          <el-table-column prop="model_type" label="类型" width="110" />
          <el-table-column prop="priority" label="优先级" width="90" />
          <el-table-column prop="timeout_seconds" label="超时" width="90" />
          <el-table-column label="健康" width="110"><template #default="{ row }"><el-tag :type="row.last_health_status === 'healthy' ? 'success' : row.last_health_status === 'degraded' ? 'danger' : 'info'">{{ row.last_health_status || '未检测' }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="openDeployment(row)">编辑</el-button></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="凭据" name="credentials">
        <el-alert title="密钥只在写入时接收，列表仅显示摘要；后台不会返回明文。" type="info" show-icon :closable="false" />
        <el-table :data="credentials" v-loading="loading" class="with-alert">
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="provider" label="Provider" width="150" />
          <el-table-column prop="scope" label="范围" width="110" />
          <el-table-column prop="secret_hint" label="密钥摘要" width="160" />
          <el-table-column prop="updated_at" label="更新时间" width="180"><template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template></el-table-column>
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" @click="removeCredential(row)">删除</el-button></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="调用账本" name="requests">
        <el-table :data="requests" v-loading="loading">
          <el-table-column prop="created_at" label="时间" width="180"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column>
          <el-table-column prop="task_name" label="任务" min-width="190" />
          <el-table-column prop="deployment_name" label="部署" min-width="170" />
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'succeeded' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column label="Tokens" width="130"><template #default="{ row }">{{ row.input_tokens }} / {{ row.output_tokens }}</template></el-table-column>
          <el-table-column prop="latency_ms" label="延迟(ms)" width="100" />
          <el-table-column prop="estimated_cost" label="估算成本" width="110" />
          <el-table-column prop="fallback_count" label="降级次数" width="90" />
          <el-table-column prop="error_code" label="错误码" min-width="140" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="credentialDialog" title="新增平台凭据" width="520px" @closed="resetCredential">
      <el-form :model="credentialForm" label-width="90px">
        <el-form-item label="名称"><el-input v-model="credentialForm.name" /></el-form-item>
        <el-form-item label="Provider"><el-input v-model="credentialForm.provider" placeholder="openai_compatible" /></el-form-item>
        <el-form-item label="范围"><el-segmented v-model="credentialForm.scope" :options="[{ label: '平台', value: 'platform' }, { label: '个人 BYOK', value: 'byok' }]" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="credentialForm.secret" type="password" show-password autocomplete="new-password" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="credentialDialog=false">取消</el-button><el-button type="primary" @click="saveCredential">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="deploymentDialog" :title="deploymentForm.id ? '编辑模型部署' : '新增模型部署'" width="620px">
      <el-form :model="deploymentForm" label-width="100px">
        <el-form-item label="部署名称"><el-input v-model="deploymentForm.name" /></el-form-item>
        <el-form-item label="Provider"><el-input v-model="deploymentForm.provider" /></el-form-item>
        <el-form-item label="远端模型"><el-input v-model="deploymentForm.remote_model" /></el-form-item>
        <el-form-item label="模型类型"><el-select v-model="deploymentForm.model_type"><el-option v-for="type in ['chat','embedding','rerank','asr','tts']" :key="type" :label="type" :value="type" /></el-select></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="deploymentForm.base_url" /></el-form-item>
        <el-form-item label="平台凭据"><el-select v-model="deploymentForm.credential" clearable><el-option v-for="item in credentials" :key="item.id" :label="`${item.name} (${item.secret_hint})`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="deploymentForm.priority" :min="0" /></el-form-item>
        <el-form-item label="超时秒数"><el-input-number v-model="deploymentForm.timeout_seconds" :min="1" :max="300" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="deploymentForm.is_active" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="deploymentDialog=false">取消</el-button><el-button type="primary" @click="saveDeployment">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Key, Plus } from '@element-plus/icons-vue';
import {
  createGatewayCredentialApi, createGatewayDeploymentApi, deleteGatewayCredentialApi,
  getGatewayAliasesApi, getGatewayCredentialsApi, getGatewayDeploymentsApi, getGatewayRequestsApi,
  updateGatewayDeploymentApi, type GatewayCredential, type ModelAlias, type ModelDeployment, type ModelRequestRecord,
} from '@/api/modules/gateway';
import { formatDateTime } from '@/utils/format';

const activeTab = ref('aliases');
const loading = ref(false);
const aliases = ref<ModelAlias[]>([]);
const deployments = ref<ModelDeployment[]>([]);
const credentials = ref<GatewayCredential[]>([]);
const requests = ref<ModelRequestRecord[]>([]);
const credentialDialog = ref(false);
const deploymentDialog = ref(false);
const credentialForm = reactive<any>({ name: '', provider: 'openai_compatible', scope: 'platform', secret: '' });
const deploymentForm = reactive<any>({ priority: 100, timeout_seconds: 30, is_active: true, model_type: 'chat' });

async function load() { loading.value = true; try { [aliases.value, deployments.value, credentials.value, requests.value] = await Promise.all([getGatewayAliasesApi(), getGatewayDeploymentsApi(), getGatewayCredentialsApi(), getGatewayRequestsApi()]); } finally { loading.value = false; } }
onMounted(load);
function reset(target: any, value: any) { Object.keys(target).forEach(key => delete target[key]); Object.assign(target, value); }
function resetCredential() { reset(credentialForm, { name: '', provider: 'openai_compatible', scope: 'platform', secret: '' }); }
function openDeployment(row?: ModelDeployment) { reset(deploymentForm, row || { name: '', provider: 'openai_compatible', remote_model: '', model_type: 'chat', base_url: '', credential: null, priority: 100, timeout_seconds: 30, capabilities: {}, is_active: true, input_price_per_million: 0, output_price_per_million: 0 }); deploymentDialog.value = true; }
async function saveCredential() { if (!credentialForm.name || !credentialForm.secret) return ElMessage.warning('请填写名称和 API Key'); await createGatewayCredentialApi(credentialForm); credentialDialog.value = false; await load(); ElMessage.success('凭据已加密保存'); }
async function removeCredential(item: GatewayCredential) { await ElMessageBox.confirm(`删除凭据“${item.name}”？`, '确认删除'); await deleteGatewayCredentialApi(item.id); await load(); }
async function saveDeployment() { if (!deploymentForm.name || !deploymentForm.remote_model || !deploymentForm.base_url) return ElMessage.warning('请完整填写部署信息'); deploymentForm.id ? await updateGatewayDeploymentApi(deploymentForm.id, deploymentForm) : await createGatewayDeploymentApi(deploymentForm); deploymentDialog.value = false; await load(); ElMessage.success('部署已保存'); }
</script>

<style scoped>
.gateway-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }
.page-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }
.page-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }
.page-header p { margin: 8px 0 0; color: #667085; }
.gateway-tabs { margin-top: 18px; padding: 0 20px 20px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }
.route-tag { margin: 2px 6px 2px 0; }
.with-alert { margin-top: 14px; }
@media (max-width: 700px) { .gateway-page { padding: 14px; } .page-header { align-items: flex-start; flex-direction: column; } }
</style>
