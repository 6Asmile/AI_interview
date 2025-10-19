<!-- src/views/ResumeGenerator.vue -->
<template>
  <div class="page-container generator-page">
    <div class="generator-card">
      <el-steps :active="activeStep" finish-status="success" align-center style="margin-bottom: 40px;">
        <el-step title="核心信息" description="填写简历关键信息" />
        <el-step title="选择模板" description="选择您心仪的简历风格" />
        <el-step title="AI 生成简历" description="预览并确认最终结果" />
      </el-steps>

      <!-- Step 1: Form -->
      <div v-if="activeStep === 0" class="step-content">
        <el-form :model="form" label-position="top" class="form-step-1">
          <el-form-item label="姓名 (必填)"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="意向岗位 (必填)"><el-input v-model="form.position" /></el-form-item>
          <el-form-item label="工作年限 (必填)">
            <el-select v-model="form.experience_years" placeholder="请选择工作年限" style="width: 100%;">
              <el-option v-for="y in 11" :key="y-1" :label="`${y-1}年`" :value="`${y-1}年`" />
            </el-select>
          </el-form-item>
          <el-form-item label="其他关键词 (选填)">
            <el-input type="textarea" :rows="3" v-model="form.keywords" placeholder="输入其他相关技能、特长、项目经验等，AI会围绕它们进行扩展..." />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 2: Template -->
      <div v-if="activeStep === 1" class="step-content template-selection">
        <div 
          v-for="template in templates" 
          :key="template.id" 
          class="template-card" 
          :class="{ 'is-selected': selectedTemplateId === template.id }"
          @click="selectedTemplateId = template.id"
        >
          <div class="template-preview">[ {{ template.name }} 预览图 ]</div>
          <div class="template-name">{{ template.name }}</div>
        </div>
      </div>
      
      <!-- Step 3: Generate -->
       <div v-if="activeStep === 2" class="step-content generate-content">
         <div v-loading="isGenerating" element-loading-text="AI 正在为您撰写简历，请稍候..." style="min-height: 200px;">
           <div v-if="generatedJson" class="preview-container">
             <h3>AI 生成预览</h3>
             <div class="mini-canvas">
               <ResumeCanvas :resume-json-prop="generatedJson" :template-id-prop="selectedTemplateId" :is-editor="false" />
             </div>
           </div>
         </div>
       </div>

      <!-- Actions -->
      <div class="actions">
        <el-button @click="prevStep" v-if="activeStep > 0 && !isGenerating">上一步</el-button>
        <el-button type="primary" @click="nextStep" v-if="activeStep < 2" :disabled="isNextDisabled">下一步</el-button>
        <el-button type="primary" @click="createResume" v-if="activeStep === 2" :loading="isCreating || isGenerating">
          完成并创建简历
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElSteps, ElStep, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElButton, ElLoading } from 'element-plus';
import { templates } from '@/resume-templates';
import { generateResumeApi } from '@/api/modules/resumeEditor';
import { createResumeApi } from '@/api/modules/resume';
import { type ResumeLayout } from '@/store/modules/resumeEditor';
import ResumeCanvas from '@/components/resume/editor/ResumeCanvas.vue';

const router = useRouter();
const activeStep = ref(0);
const form = reactive({ name: '', position: '', experience_years: '', keywords: '' });
const selectedTemplateId = ref(templates[0]?.id || 'default');
const isGenerating = ref(false);
const isCreating = ref(false);
const generatedJson = ref<ResumeLayout | null>(null);

const isNextDisabled = computed(() => {
    if (activeStep.value === 0) {
        return !form.name || !form.position || !form.experience_years;
    }
    return false;
});

const nextStep = async () => {
  if (activeStep.value === 1) {
    isGenerating.value = true;
    generatedJson.value = null;
    try {
      generatedJson.value = await generateResumeApi(form.name, form.position, form.experience_years, form.keywords);
    } catch (e) {
      ElMessage.error('AI 生成失败，请返回上一步重试');
      // optional: stay on the current step
      // return;
    } finally {
      isGenerating.value = false;
    }
  }
  if (activeStep.value < 2) activeStep.value++;
};

const prevStep = () => {
  if (activeStep.value > 0) activeStep.value--;
};

const createResume = async () => {
  if (!generatedJson.value) {
    ElMessage.error('没有可创建的简历内容');
    return;
  }
  isCreating.value = true;
  try {
    // 【核心修复】使用 as any 来绕过严格的类型检查
    await createResumeApi({
      title: `${form.name}的AI生成简历-${form.position}`,
      status: 'draft',
      content_json: generatedJson.value,
      template_name: selectedTemplateId.value,
    } as any);
    ElMessage.success('简历创建成功！');
    router.push({ name: 'ResumeManagement' });
  } catch(e) {
    ElMessage.error('创建简历失败');
  } finally {
    isCreating.value = false;
  }
};
</script>

<style scoped>
.generator-page { padding: 30px; background-color: #f9faff; }
.generator-card { background-color: #fff; padding: 30px 40px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
.step-content { margin-top: 40px; }
.form-step-1 { max-width: 500px; margin: 0 auto; }
.actions { margin-top: 40px; text-align: center; }
.template-selection { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 20px; }
.template-card { border: 2px solid #e0e0e0; border-radius: 8px; cursor: pointer; transition: all 0.2s; overflow: hidden; }
.template-card.is-selected { border-color: var(--el-color-primary); box-shadow: 0 0 10px var(--el-color-primary-light-7); }
.template-preview { height: 250px; background-color: #f5f7fa; display: flex; align-items: center; justify-content: center; color: #ccc; }
.template-name { text-align: center; padding: 10px; font-size: 14px; }
.preview-container { border: 1px solid #eee; padding: 10px; }
.mini-canvas { transform: scale(0.5); transform-origin: top left; width: 200%; height: 200%; }
</style>