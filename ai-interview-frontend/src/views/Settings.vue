<!-- src/views/Settings.vue -->
<template>
  <div class="page-container">
    <el-card v-loading="isLoading">
      <template #header>
        <div class="page-card-header">
          <span>AI 设置</span>
          <el-button type="primary" @click="saveSettings" :loading="isSaving">保存设置</el-button>
        </div>
      </template>

      <el-form label-position="top" v-if="!isLoading">
        <!-- 1. 默认模型选择 -->
        <el-form-item label="默认对话模型">
          <el-select v-model="settingsForm.ai_model_id" placeholder="选择您偏好的对话模型" clearable style="width: 100%;">
            <el-option
              v-for="model in allModels"
              :key="model.id"
              :label="`${model.name} (${model.model_slug})`"
              :value="model.id"
            />
          </el-select>
          <p class="form-tip">所有 AI 功能（面试、润色、分析）将优先使用您选择的默认模型。如果留空，将使用系统默认模型。</p>
        </el-form-item>
        
        <el-divider />

        <!-- 2. API Key 管理 -->
        <h3>API Key 管理</h3>
        <p class="form-tip">您可以为不同的模型配置独立的 API Key。当使用某个模型时，系统会优先使用您在此处提供的 Key。</p>
        
        <el-row :gutter="20">
          <el-col :span="12" v-for="model in allModels" :key="`key-${model.id}`">
            <el-form-item :label="model.name">
              <el-input 
                v-model="settingsForm.api_keys[model.id]" 
                :placeholder="`输入 ${model.name} 的 API Key`"
                show-password
                clearable
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { getAISettingsApi, updateAISettingsApi, getAIModelsApi, type AIModelItem, type UpdateAISettingsData } from '@/api/modules/system';
import { ElMessage } from 'element-plus';

const isLoading = ref(true);
const isSaving = ref(false);
const allModels = ref<AIModelItem[]>([]);

const settingsForm = reactive({
    ai_model_id: null as number | null,
    api_keys: {} as Record<string, string>,
});

onMounted(async () => {
  isLoading.value = true;
  try {
    const [modelsRes, settingsRes] = await Promise.all([
      getAIModelsApi(),
      getAISettingsApi(),
    ]);

    allModels.value = modelsRes;
    
    // --- 【核心修复】确保 api_keys 对象的完整性 ---

    // 1. 获取用户已保存的 keys
    const savedKeys = settingsRes.api_keys || {};
    const newApiKeys: Record<string, string> = {};

    // 2. 遍历所有从后端获取的模型
    for (const model of modelsRes) {
        // 无论用户是否已保存该模型的 key，都在新对象中为其创建一个属性
        // 如果用户已保存，则使用保存的值；否则，使用空字符串
        newApiKeys[model.id] = savedKeys[model.id] || '';
    }

    // 3. 将这个结构完整的、响应式的对象赋值给表单
    settingsForm.api_keys = newApiKeys;
    settingsForm.ai_model_id = settingsRes.ai_model?.id || null;

  } catch (error) {
    ElMessage.error('加载设置失败');
  } finally {
    isLoading.value = false;
  }
});

const saveSettings = async () => {
  isSaving.value = true;
  try {
    // 在发送前，可以清理掉值为空字符串的 key，减小 payload 体积
    const cleanedApiKeys: Record<string, string> = {};
    for (const modelId in settingsForm.api_keys) {
        if (settingsForm.api_keys[modelId]) {
            cleanedApiKeys[modelId] = settingsForm.api_keys[modelId];
        }
    }

    const payload: UpdateAISettingsData = {
        ai_model_id: settingsForm.ai_model_id,
        api_keys: cleanedApiKeys,
    };

    await updateAISettingsApi(payload);
    ElMessage.success('设置已成功保存！');
  } catch (error) {
    ElMessage.error('保存设置失败');
  } finally {
    isSaving.value = false;
  }
};
</script>

<style scoped>
.page-container { padding: 20px; }
.page-card-header { display: flex; justify-content: space-between; align-items: center; }
.form-tip { font-size: 12px; color: #999; margin-top: 4px; }
h3 { margin-top: 20px; margin-bottom: 8px; }
</style>