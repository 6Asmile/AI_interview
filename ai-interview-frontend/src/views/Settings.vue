<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { 
  ElMessage, ElForm, ElFormItem, ElSelect, ElOption, ElInput, 
  ElButton, ElCard, ElRow, ElCol 
} from 'element-plus';
import { getAISettingsApi, updateAISettingsApi, getAIModelsApi } from '@/api/modules/system';
import type { AIModelItem, AISettingsData } from '@/api/modules/system';

// --- 响应式状态 ---
const settingsForm = ref<Partial<AISettingsData> & { ai_model_id?: number | null }>({
  ai_model_id: null,
  api_keys: {},
});
const availableModels = ref<AIModelItem[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);

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
      ai_model_id: settings.ai_model ? settings.ai_model.id : null,
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
    const payload: { ai_model_id?: number | null; api_keys?: Record<string, string> } = {
      ai_model_id: settingsForm.value.ai_model_id,
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
        <el-form-item label="默认 AI 模型">
          <p class="form-item-description">
            所有 AI 功能（面试、润色、分析）将优先使用您选择的默认模型。如果留空，将使用系统默认模型。
          </p>
          <el-select v-model="settingsForm.ai_model_id" placeholder="请选择默认模型" clearable style="width: 100%;">
            <el-option
              v-for="model in availableModels"
              :key="model.id"
              :label="model.name"
              :value="model.id"
            />
          </el-select>
        </el-form-item>

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
  align-items: center;
}
.model-name {
  color: #606266;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>