<!-- src/views/Settings.vue -->
<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>AI 模型设置</span>
        </div>
      </template>

      <el-form 
        v-if="!loading"
        ref="settingsFormRef" 
        :model="settingsForm" 
        label-width="120px" 
        style="max-width: 600px"
      >
        <el-form-item label="选择模型">
          <el-select v-model="settingsForm.ai_model" placeholder="请选择AI模型">
            <el-option label="DeepSeek Chat" value="deepseek-chat" />
            <!-- 未来可以添加更多模型选项 -->
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input 
            v-model="settingsForm.api_key" 
            type="password"
            show-password
            placeholder="填写您的 API Key (将安全存储)" 
          />
          <div class="form-tip">
            如果您填写了自己的 API Key，面试将使用您的 Key。如果留空，将使用系统默认配置。
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存设置</el-button>
        </el-form-item>
      </el-form>
      <el-skeleton :rows="5" animated v-if="loading" />
    </el-card>
  </div>
</template>

// src/views/Settings.vue -> <script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance } from 'element-plus';
// 1. 导入 API 函数
import { getAISettingsApi, updateAISettingsApi, type AISettingsData } from '@/api/modules/system';

const loading = ref(true);
const saving = ref(false);
const settingsFormRef = ref<FormInstance>();
const settingsForm = reactive<AISettingsData>({
  ai_model: 'deepseek-chat',
  api_key: '',
});

// 2. 实现获取设置的逻辑
const fetchSettings = async () => {
  loading.value = true;
  try {
    const remoteSettings = await getAISettingsApi();
    Object.assign(settingsForm, remoteSettings);
  } catch (error) {
    console.error('获取AI设置失败', error);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchSettings();
});

// 3. 实现保存设置的逻辑
const handleSave = async () => {
  saving.value = true;
  try {
    await updateAISettingsApi(settingsForm);
    ElMessage.success('设置已成功保存！');
    // 可选：保存后可以重新获取一次数据
    await fetchSettings();
  } catch (error) {
    console.error('保存AI设置失败', error);
  } finally {
    saving.value = false;
  }
};
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
</style>