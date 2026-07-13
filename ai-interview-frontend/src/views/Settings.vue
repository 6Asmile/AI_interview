<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { 
  ElMessage, ElForm, ElFormItem, ElSelect, ElOption, ElInput, 
  ElButton, ElCard, ElRow, ElCol, ElTag, ElSpace
} from 'element-plus';
import { getAISettingsApi, updateAISettingsApi, getAIModelsApi, checkAIModelGatewayHealthApi } from '@/api/modules/system';
import type { AIModelItem, AISettingsData, AIModelGatewayHealthResult } from '@/api/modules/system';

// --- 响应式状态 ---
type SettingsForm = Partial<AISettingsData> & {
  ai_model_id?: number | null;
  chat_model_id?: number | null;
  embedding_model_id?: number | null;
  rerank_model_id?: number | null;
  asr_model_id?: number | null;
  tts_model_id?: number | null;
};

const settingsForm = ref<SettingsForm>({
  ai_model_id: null,
  chat_model_id: null,
  embedding_model_id: null,
  rerank_model_id: null,
  asr_model_id: null,
  tts_model_id: null,
  api_keys: {},
});
const availableModels = ref<AIModelItem[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);
const healthChecking = ref<Record<string, boolean>>({});
const healthResults = ref<Record<string, AIModelGatewayHealthResult>>({});
const chatModels = computed(() => availableModels.value.filter(model => model.model_type === 'chat'));
const embeddingModels = computed(() => availableModels.value.filter(model => model.model_type === 'embedding'));
const rerankModels = computed(() => availableModels.value.filter(model => model.model_type === 'rerank'));
const asrModels = computed(() => availableModels.value.filter(model => model.model_type === 'asr'));
const ttsModels = computed(() => availableModels.value.filter(model => model.model_type === 'tts'));

// --- 数据获取 ---
const fetchData = async () => {
  isLoading.value = true;
  try {
    const [settings, modelsResponse] = await Promise.all([
      getAISettingsApi(),
      getAIModelsApi(),
    ]);

    availableModels.value = modelsResponse.results;
    
    settingsForm.value = {
      ai_model_id: settings.chat_model?.id || settings.ai_model?.id || null,
      chat_model_id: settings.chat_model?.id || settings.ai_model?.id || null,
      embedding_model_id: settings.embedding_model?.id || null,
      rerank_model_id: settings.rerank_model?.id || null,
      asr_model_id: settings.asr_model?.id || null,
      tts_model_id: settings.tts_model?.id || null,
      api_keys: { ...settings.api_keys },
    };

  } catch (error) {
    ElMessage.error('加载AI设置失败');
    console.error(error);
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchData);

// --- 事件处理 ---
const handleSave = async () => {
  isSaving.value = true;
  try {
    const payload: { ai_model_id?: number | null; chat_model_id?: number | null; embedding_model_id?: number | null; rerank_model_id?: number | null; asr_model_id?: number | null; tts_model_id?: number | null; api_keys?: Record<string, string> } = {
      ai_model_id: settingsForm.value.chat_model_id,
      chat_model_id: settingsForm.value.chat_model_id,
      embedding_model_id: settingsForm.value.embedding_model_id,
      rerank_model_id: settingsForm.value.rerank_model_id,
      asr_model_id: settingsForm.value.asr_model_id,
      tts_model_id: settingsForm.value.tts_model_id,
      api_keys: settingsForm.value.api_keys,
    };
    await updateAISettingsApi(payload);
    ElMessage.success('AI 设置已成功保存！');
    fetchData();
  } catch (error) {
    ElMessage.error('保存失败，请稍后再试');
  } finally {
    isSaving.value = false;
  }
};

const handleHealthCheck = async (modelType: AIModelItem['model_type']) => {
  healthChecking.value[modelType] = true;
  try {
    const result = await checkAIModelGatewayHealthApi(modelType);
    healthResults.value[modelType] = result;
    if (result.ok) {
      ElMessage.success(`${modelType} 模型连通性正常`);
    } else {
      ElMessage.warning(`${modelType} 模型检测失败：${result.error || '配置不可用'}`);
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || `${modelType} 模型检测失败`);
  } finally {
    healthChecking.value[modelType] = false;
  }
};

const healthTagType = (modelType: AIModelItem['model_type']) => {
  const result = healthResults.value[modelType];
  if (!result) return 'info';
  return result.ok ? 'success' : 'danger';
};

const healthText = (modelType: AIModelItem['model_type']) => {
  const result = healthResults.value[modelType];
  if (!result) return '未检测';
  if (result.ok) {
    const dimension = result.dimension ? ` · ${result.dimension}维` : '';
    return `正常 · ${result.latency_ms ?? '-'}ms${dimension}`;
  }
  return result.error || '不可用';
};
</script>

<template>
  <div class="settings-container">
    <el-card shadow="never" v-loading="isLoading">
      <template #header>
        <div class="card-header">
          <span>AI 设置</span>
          <el-button type="primary" :loading="isSaving" @click="handleSave">保存设置</el-button>
        </div>
      </template>

      <el-form :model="settingsForm" label-position="top">
        <el-form-item label="对话模型">
          <p class="form-item-description">
            面试出题、回答评估、报告生成等对话型 AI 功能将使用该模型。
          </p>
          <el-space fill style="width: 100%;">
            <el-select v-model="settingsForm.chat_model_id" placeholder="请选择对话模型" clearable style="width: 100%;">
              <el-option
                v-for="model in chatModels"
                :key="model.id"
                :label="`${model.name} · ${model.provider}`"
                :value="model.id"
              />
            </el-select>
            <div class="health-row">
              <el-button size="small" :loading="healthChecking.chat" @click="handleHealthCheck('chat')">检测</el-button>
              <el-tag size="small" :type="healthTagType('chat')">{{ healthText('chat') }}</el-tag>
            </div>
          </el-space>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <el-form-item label="Embedding 模型">
              <p class="form-item-description">
                知识库索引和向量召回使用该模型，默认推荐阿里云 text-embedding-v3。
              </p>
              <el-select v-model="settingsForm.embedding_model_id" placeholder="请选择 Embedding 模型" clearable style="width: 100%;">
                <el-option
                  v-for="model in embeddingModels"
                  :key="model.id"
                  :label="`${model.name} · ${model.dimension || '-'}维`"
                  :value="model.id"
                />
              </el-select>
              <div class="health-row">
                <el-button size="small" :loading="healthChecking.embedding" @click="handleHealthCheck('embedding')">检测</el-button>
                <el-tag size="small" :type="healthTagType('embedding')">{{ healthText('embedding') }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="Rerank 模型">
              <p class="form-item-description">
                知识库召回后使用该模型重排，默认推荐阿里云 qwen-rerank。
              </p>
              <el-select v-model="settingsForm.rerank_model_id" placeholder="请选择 Rerank 模型" clearable style="width: 100%;">
                <el-option
                  v-for="model in rerankModels"
                  :key="model.id"
                  :label="`${model.name} · ${model.provider}`"
                  :value="model.id"
                />
              </el-select>
              <div class="health-row">
                <el-button size="small" :loading="healthChecking.rerank" @click="handleHealthCheck('rerank')">检测</el-button>
                <el-tag size="small" :type="healthTagType('rerank')">{{ healthText('rerank') }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <el-form-item label="ASR 语音识别模型">
              <p class="form-item-description">
                面试语音回答转写使用该模型。未配置时不会生成后端转写，前端可继续手动输入。
              </p>
              <el-select v-model="settingsForm.asr_model_id" placeholder="请选择 ASR 模型" clearable style="width: 100%;">
                <el-option
                  v-for="model in asrModels"
                  :key="model.id"
                  :label="`${model.name} · ${model.provider}`"
                  :value="model.id"
                />
              </el-select>
              <div class="health-row">
                <el-button size="small" :loading="healthChecking.asr" @click="handleHealthCheck('asr')">检测</el-button>
                <el-tag size="small" :type="healthTagType('asr')">{{ healthText('asr') }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="TTS 语音合成模型">
              <p class="form-item-description">
                AI 面试官问题播放优先使用该模型生成语音；失败时自动使用浏览器 TTS。
              </p>
              <el-select v-model="settingsForm.tts_model_id" placeholder="请选择 TTS 模型" clearable style="width: 100%;">
                <el-option
                  v-for="model in ttsModels"
                  :key="model.id"
                  :label="`${model.name} · ${model.provider}`"
                  :value="model.id"
                />
              </el-select>
              <div class="health-row">
                <el-button size="small" :loading="healthChecking.tts" @click="handleHealthCheck('tts')">检测</el-button>
                <el-tag size="small" :type="healthTagType('tts')">{{ healthText('tts') }}</el-tag>
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="API Key 管理">
          <p class="form-item-description">
            您可以为不同的模型配置独立的 API Key。当使用某个模型时，系统会优先使用您在此处提供的 Key。
          </p>
          
          <!-- 【核心修复】使用 el-row 和 el-col 进行栅格布局 -->
          <div class="api-key-list">
            <el-row 
              v-for="model in availableModels" 
              :key="`key-${model.id}`" 
              class="api-key-item"
              :gutter="20"
              align="middle"
            >
              <el-col :span="8" class="model-name-col">
                <span class="model-name">{{ model.name }}</span>
                <small>{{ model.model_type }} · {{ model.provider }}</small>
              </el-col>
              <el-col :span="16">
                <el-input
                  v-model="settingsForm.api_keys![model.id]"
                  :placeholder="`输入 ${model.name} 的 API Key`"
                  show-password
                  clearable
                />
              </el-col>
            </el-row>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.settings-container {
  padding: 24px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.form-item-description {
  font-size: 0.85rem;
  color: #909399;
  margin-top: 0;
  margin-bottom: 8px;
  line-height: 1.5;
}

/* 【核心修复】API Key 列表和项目的样式 */
.api-key-list {
  width: 100%;
}
.api-key-item {
  margin-bottom: 16px;
}
.model-name-col {
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.model-name {
  color: #606266;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.model-name-col small {
  color: #909399;
  font-size: 0.75rem;
  margin-top: 3px;
}
.health-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.health-row .el-tag {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
