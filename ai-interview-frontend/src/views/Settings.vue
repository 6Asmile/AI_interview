<template>
  <div class="page-container">
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>AI 模型设置</span>
        </div>
      </template>
    
      <div v-if="!loading" style="max-width: 600px">
        <el-form 
          ref="settingsFormRef" 
          :model="settingsForm" 
          label-width="120px" 
        >
          <el-form-item label="选择模型">
            <!-- 下拉框现在是动态生成的 -->
            <el-select v-model="settingsForm.ai_model_id" placeholder="请选择AI模型" clearable>
              <el-option 
                v-for="model in aiModelList"
                :key="model.id"
                :label="model.name"
                :value="model.id"
              >
                <span style="float: left">{{ model.name }}</span>
                <span style="float: right; color: #8492a6; font-size: 13px">{{ model.model_slug }}</span>
              </el-option>
            </el-select>
             <div class="form-tip">
                选择您偏好的对话模型。如果留空，将使用系统默认模型。
              </div>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input 
              v-model="settingsForm.api_key" 
              type="password"
              show-password
              placeholder="填写您的 API Key (将安全存储)" 
            />
            <div class="form-tip">
              如果您填写了自己的 API Key，面试将优先使用您的 Key。如果留空，将使用系统默认配置。
            </div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSave" :loading="saving">保存设置</el-button>
          </el-form-item>
        </el-form>
      </div>
      <el-skeleton :rows="5" animated v-if="loading" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance } from 'element-plus';
import { 
  getAISettingsApi, 
  updateAISettingsApi, 
  getAIModelsApi, // 导入新 API
  type UpdateAISettingsData,
  type AIModelItem
} from '@/api/modules/system';

const loading = ref(true);
const saving = ref(false);
const settingsFormRef = ref<FormInstance>();

// 存储从后端获取的所有可用 AI 模型
const aiModelList = ref<AIModelItem[]>([]);

// 表单数据现在只包含需要提交的字段
const settingsForm = reactive<UpdateAISettingsData>({
  ai_model_id: null,
  api_key: '',
});

// 获取所有数据
const fetchData = async () => {
  loading.value = true;
  try {
    // 并行获取用户当前的设置和系统可用的模型列表
    const [settings, models] = await Promise.all([
      getAISettingsApi(),
      getAIModelsApi(),
    ]);
    
    // 填充表单
    settingsForm.api_key = settings.api_key;
    settingsForm.ai_model_id = settings.ai_model?.id || null;
    
    // 填充模型列表
    aiModelList.value = models;
  } catch (error) {
    console.error('获取AI设置或模型列表失败', error);
    ElMessage.error('数据加载失败');
  } finally {
    loading.value = false;
  }
};

onMounted(fetchData);

const handleSave = async () => {
  saving.value = true;
  try {
    await updateAISettingsApi(settingsForm);
    ElMessage.success('设置已成功保存！');
    // 保存后重新获取一次数据，以确保显示正确
    await fetchData(); 
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
  margin-top: 5px;
}
</style>