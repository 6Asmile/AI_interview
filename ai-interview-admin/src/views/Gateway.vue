<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "@/api";
const loading = ref(false);
const tab = ref("deployments");
const summary = ref<any>({});
const data = reactive<Record<string, any[]>>({
  credentials: [],
  deployments: [],
  aliases: [],
  routes: [],
  budgets: [],
  ledger: [],
});
const dialog = ref(false);
const editId = ref<number | null>(null);
const form = reactive<any>({
  name: "",
  provider: "openai_compatible",
  secret: "",
  remote_model: "",
  model_type: "chat",
  base_url: "",
  credential_id: null,
  context_window: null,
  tokenizer_family: "",
  tokenizer_name: "",
  priority: 100,
  timeout_seconds: 30,
  slug: "",
  description: "",
  alias_id: null,
  strategy: "priority",
  total_timeout_seconds: 45,
  max_attempts: 2,
  target_ids: [],
  operation_reason: "",
});
const load = async () => {
  loading.value = true;
  try {
    const results = await Promise.all([
      api.get("/model-gateway/summary/"),
      ...Object.keys(data).map((key) => api.get(`/model-gateway/${key}/`)),
    ]);
    summary.value = results[0];
    Object.keys(data).forEach((key, index) => (data[key] = results[index + 1]));
  } finally {
    loading.value = false;
  }
};
const openCreate = () => {
  editId.value = null;
  Object.assign(form, {
    name: "",
    provider: "openai_compatible",
    secret: "",
    remote_model: "",
    model_type: "chat",
    base_url: "",
    credential_id: null,
    context_window: null,
    tokenizer_family: "",
    tokenizer_name: "",
    priority: 100,
    timeout_seconds: 30,
    slug: "",
    description: "",
    alias_id: null,
    strategy: "priority",
    total_timeout_seconds: 45,
    max_attempts: 2,
    target_ids: [],
    operation_reason: "",
  });
  dialog.value = true;
};
const openDeploymentEdit = (row: any) => {
  editId.value = row.id;
  Object.assign(form, { ...row, operation_reason: "", target_ids: [] });
  dialog.value = true;
};
const create = async () => {
  const payload = {
    ...form,
    targets: form.target_ids.map((id: number) => ({
      deployment_id: id,
      weight: 100,
    })),
  };
  const options = { headers: { "Idempotency-Key": crypto.randomUUID() } };
  if (editId.value) {
    await api.patch(
      `/model-gateway/${tab.value}/${editId.value}/`,
      payload,
      options,
    );
  } else {
    await api.post(`/model-gateway/${tab.value}/`, payload, options);
  }
  dialog.value = false;
  ElMessage.success(editId.value ? "网关配置已更新。" : "网关配置已创建。");
  await load();
};
const toggle = async (resource: string, row: any) => {
  const { value } = await ElMessageBox.prompt(
    "请输入启用状态变更原因",
    "变更配置状态",
    { inputType: "textarea" },
  );
  await api.patch(`/model-gateway/${resource}/${row.id}/`, {
    is_active: !row.is_active,
    operation_reason: value,
  });
  await load();
};
const rotate = async (row: any) => {
  const result = await ElMessageBox.prompt(
    "输入新的平台密钥。完整密钥不会再次返回。",
    "轮换凭据",
    { inputType: "password" },
  );
  const reason = await ElMessageBox.prompt("请输入凭据轮换原因", "安全确认", {
    inputType: "textarea",
  });
  await api.patch(`/model-gateway/credentials/${row.id}/`, {
    secret: result.value,
    operation_reason: reason.value,
  });
  ElMessage.success("凭据已轮换。");
  await load();
};
onMounted(load);
</script>
<template>
  <div class="page" v-loading="loading">
    <header class="page-header">
      <div>
        <h1>模型网关</h1>
        <p>
          平台凭据、模型部署、任务别名、路由策略、预算和调用账本统一管理，密钥永不回传。
        </p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <section class="metric-band">
      <div class="metric">
        <span>模型部署</span><strong>{{ summary.deployments || 0 }}</strong
        ><small>{{ summary.healthy_deployments || 0 }} 个健康</small>
      </div>
      <div class="metric">
        <span>活动凭据</span
        ><strong>{{ summary.active_credentials || 0 }}</strong
        ><small>只显示密钥尾号</small>
      </div>
      <div class="metric">
        <span>今日请求</span><strong>{{ summary.requests_today || 0 }}</strong
        ><small>统一调用账本</small>
      </div>
      <div class="metric">
        <span>今日失败</span
        ><strong class="danger-text">{{
          summary.failed_requests_today || 0
        }}</strong
        ><small>{{ summary.active_budgets || 0 }} 个活动预算</small>
      </div>
    </section>
    <el-tabs v-model="tab" class="gateway-tabs"
      ><el-tab-pane label="部署" name="deployments"
        ><div class="tab-actions">
          <el-button type="primary" @click="openCreate">新增部署</el-button>
        </div>
        <div class="data-surface">
          <el-table :data="data.deployments"
            ><el-table-column prop="name" label="部署" /><el-table-column
              prop="provider"
              label="Provider"
            /><el-table-column
              prop="remote_model"
              label="远端模型"
            /><el-table-column
              prop="model_type"
              label="类型"
              width="100"
            /><el-table-column
              prop="context_window"
              label="Context"
              width="100"
            /><el-table-column label="Tokenizer" min-width="150"
              ><template #default="{ row }">{{
                row.tokenizer_family && row.tokenizer_name
                  ? `${row.tokenizer_family}:${row.tokenizer_name}`
                  : "未配置"
              }}</template></el-table-column
            ><el-table-column
              prop="last_health_status"
              label="健康"
              width="100"
            /><el-table-column
              prop="priority"
              label="优先级"
              width="90"
            /><el-table-column label="操作" width="130"
              ><template #default="{ row }"
                ><el-button link type="primary" @click="openDeploymentEdit(row)"
                  >编辑</el-button
                ><el-button link @click="toggle('deployments', row)">{{
                  row.is_active ? "停用" : "启用"
                }}</el-button></template
              ></el-table-column
            ></el-table
          >
        </div></el-tab-pane
      ><el-tab-pane label="凭据" name="credentials"
        ><div class="tab-actions">
          <el-button type="primary" @click="openCreate">新增凭据</el-button>
        </div>
        <div class="data-surface">
          <el-table :data="data.credentials"
            ><el-table-column prop="name" label="名称" /><el-table-column
              prop="provider"
              label="Provider"
            /><el-table-column
              prop="secret_hint"
              label="密钥尾号"
            /><el-table-column
              prop="last_verified_at"
              label="最近验证"
            /><el-table-column label="操作" width="150"
              ><template #default="{ row }"
                ><el-button link type="primary" @click="rotate(row)"
                  >轮换</el-button
                ><el-button link @click="toggle('credentials', row)">{{
                  row.is_active ? "停用" : "启用"
                }}</el-button></template
              ></el-table-column
            ></el-table
          >
        </div></el-tab-pane
      ><el-tab-pane label="任务别名" name="aliases"
        ><div class="tab-actions">
          <el-button type="primary" @click="openCreate">新增别名</el-button>
        </div>
        <div class="data-surface">
          <el-table :data="data.aliases"
            ><el-table-column prop="slug" label="任务别名" /><el-table-column
              prop="name"
              label="名称"
            /><el-table-column prop="model_type" label="类型" /><el-table-column
              prop="description"
              label="说明"
            /><el-table-column label="操作" width="90"
              ><template #default="{ row }"
                ><el-button link @click="toggle('aliases', row)">{{
                  row.is_active ? "停用" : "启用"
                }}</el-button></template
              ></el-table-column
            ></el-table
          >
        </div></el-tab-pane
      ><el-tab-pane label="路由策略" name="routes"
        ><div class="tab-actions">
          <el-button type="primary" @click="openCreate">新增路由</el-button>
        </div>
        <div class="data-surface">
          <el-table :data="data.routes"
            ><el-table-column prop="alias" label="别名" /><el-table-column
              prop="strategy"
              label="策略"
            /><el-table-column
              prop="max_attempts"
              label="尝试"
            /><el-table-column label="目标"
              ><template #default="{ row }">{{
                row.targets.map((x: any) => x.deployment).join(" → ")
              }}</template></el-table-column
            ><el-table-column label="操作"
              ><template #default="{ row }"
                ><el-button link @click="toggle('routes', row)">{{
                  row.is_active ? "停用" : "启用"
                }}</el-button></template
              ></el-table-column
            ></el-table
          >
        </div></el-tab-pane
      ><el-tab-pane label="预算" name="budgets"
        ><div class="data-surface">
          <el-table :data="data.budgets"
            ><el-table-column prop="user_email" label="用户" /><el-table-column
              prop="monthly_token_limit"
              label="Token 上限" /><el-table-column
              prop="used_input_tokens"
              label="输入已用" /><el-table-column
              prop="used_output_tokens"
              label="输出已用" /><el-table-column
              prop="monthly_cost_limit"
              label="成本上限" /><el-table-column
              prop="used_cost"
              label="已用成本"
          /></el-table></div></el-tab-pane
      ><el-tab-pane label="调用账本" name="ledger"
        ><div class="data-surface">
          <el-table :data="data.ledger"
            ><el-table-column prop="task_name" label="任务" /><el-table-column
              prop="alias"
              label="别名" /><el-table-column
              prop="deployment"
              label="部署" /><el-table-column
              prop="status"
              label="状态" /><el-table-column
              prop="latency_ms"
              label="耗时" /><el-table-column
              prop="estimated_cost"
              label="成本" /><el-table-column prop="error_code" label="错误"
          /></el-table></div></el-tab-pane
    ></el-tabs>
    <el-dialog
      v-model="dialog"
      :title="editId ? '编辑模型部署' : '新增模型网关配置'"
      width="600px"
      ><el-form label-position="top"
        ><template v-if="tab === 'credentials'"
          ><el-form-item label="名称"
            ><el-input v-model="form.name" /></el-form-item
          ><el-form-item label="Provider"
            ><el-input v-model="form.provider" /></el-form-item
          ><el-form-item label="平台密钥"
            ><el-input
              v-model="form.secret"
              type="password"
              show-password /></el-form-item></template
        ><template v-if="tab === 'deployments'"
          ><el-form-item label="部署名称"
            ><el-input v-model="form.name" /></el-form-item
          ><el-form-item label="Provider"
            ><el-input v-model="form.provider" /></el-form-item
          ><el-form-item label="远端模型"
            ><el-input v-model="form.remote_model" /></el-form-item
          ><el-form-item label="模型类型"
            ><el-select v-model="form.model_type"
              ><el-option
                v-for="type in ['chat', 'embedding', 'rerank', 'asr', 'tts']"
                :key="type"
                :label="type"
                :value="type" /></el-select></el-form-item
          ><el-form-item label="Base URL"
            ><el-input v-model="form.base_url" /></el-form-item
          ><el-form-item label="凭据"
            ><el-select v-model="form.credential_id" style="width: 100%"
              ><el-option
                v-for="item in data.credentials"
                :key="item.id"
                :label="item.name"
                :value="item.id" /></el-select></el-form-item
          ><el-form-item label="Context Window"
            ><el-input-number
              v-model="form.context_window"
              :min="1024"
              :max="2000000" /></el-form-item
          ><el-form-item label="Tokenizer Family"
            ><el-select v-model="form.tokenizer_family" style="width: 100%"
              ><el-option label="tiktoken" value="tiktoken" /><el-option
                label="Hugging Face"
                value="huggingface" /><el-option
                label="近似计数"
                value="approximate" /></el-select></el-form-item
          ><el-form-item label="Tokenizer 标识"
            ><el-input
              v-model="form.tokenizer_name"
              placeholder="例如 cl100k_base 或本地 Hugging Face 模型名" /></el-form-item></template
        ><template v-if="tab === 'aliases'"
          ><el-form-item label="任务别名"
            ><el-input
              v-model="form.slug"
              placeholder="interview.generate.quality" /></el-form-item
          ><el-form-item label="名称"
            ><el-input v-model="form.name" /></el-form-item
          ><el-form-item label="模型类型"
            ><el-select v-model="form.model_type"
              ><el-option
                v-for="type in ['chat', 'embedding', 'rerank', 'asr', 'tts']"
                :key="type"
                :label="type"
                :value="type" /></el-select></el-form-item
          ><el-form-item label="说明"
            ><el-input
              v-model="form.description"
              type="textarea" /></el-form-item></template
        ><template v-if="tab === 'routes'"
          ><el-form-item label="任务别名"
            ><el-select v-model="form.alias_id" style="width: 100%"
              ><el-option
                v-for="item in data.aliases"
                :key="item.id"
                :label="item.slug"
                :value="item.id" /></el-select></el-form-item
          ><el-form-item label="策略"
            ><el-radio-group v-model="form.strategy"
              ><el-radio-button value="priority">优先级故障转移</el-radio-button
              ><el-radio-button value="weighted"
                >加权</el-radio-button
              ></el-radio-group
            ></el-form-item
          ><el-form-item label="部署链"
            ><el-select v-model="form.target_ids" multiple style="width: 100%"
              ><el-option
                v-for="item in data.deployments"
                :key="item.id"
                :label="item.name"
                :value="item.id" /></el-select></el-form-item></template
        ><el-form-item label="操作原因"
          ><el-input
            v-model="form.operation_reason"
            type="textarea" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!form.operation_reason.trim()"
          @click="create"
          >{{ editId ? "保存" : "创建" }}</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>
<style scoped>
.gateway-tabs {
  margin-top: 22px;
}
.tab-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
</style>
