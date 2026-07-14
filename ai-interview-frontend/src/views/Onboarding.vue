<template>
  <main class="onboarding-page">
    <header><router-link to="/">IFaceOff</router-link><span>首次使用设置</span></header>
    <section class="onboarding-panel">
      <el-steps :active="step" finish-status="success" simple><el-step title="求职目标"/><el-step title="准备材料"/><el-step title="开始闭环"/></el-steps>
      <div v-if="step === 0" class="step-body">
        <h1>你希望准备什么岗位？</h1><p>这些信息用于工作台默认筛选，不会替代真实 JD。</p>
        <el-input v-model="headline" placeholder="例如：Agent 开发工程师" />
        <el-select v-model="targetRoles" multiple filterable allow-create default-first-option placeholder="添加目标岗位"><el-option v-for="item in targetRoles" :key="item" :label="item" :value="item" /></el-select>
      </div>
      <div v-else-if="step === 1" class="step-body">
        <h1>建立可信材料</h1><p>先上传并确认简历，或到求职工作台保存一个真实岗位 JD。</p>
        <div class="choice-row"><el-button @click="router.push('/dashboard/resumes')">管理简历</el-button><el-button @click="router.push('/dashboard/career')">添加目标岗位</el-button></div>
      </div>
      <div v-else class="step-body">
        <h1>准备完成</h1><p>之后可以从简历诊断或模拟面试进入完整求职闭环。</p>
        <div class="choice-row"><el-button @click="router.push('/dashboard/ai-diagnosis')">简历诊断</el-button><el-button type="primary" @click="router.push('/dashboard/interviews')">模拟面试</el-button></div>
      </div>
      <footer><el-button v-if="step" @click="step--">上一步</el-button><el-button v-if="step < 2" type="primary" @click="next">下一步</el-button><el-button v-else type="primary" :loading="finishing" @click="finish">进入工作台</el-button></footer>
    </section>
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'; import { useRouter } from 'vue-router'; import { completeOnboardingApi, updateUserProfileApi } from '@/api/modules/user'; import { useAuthStore } from '@/store/modules/auth';
const router=useRouter(); const auth=useAuthStore(); const step=ref(0); const headline=ref(auth.user?.headline||''); const targetRoles=ref<string[]>(auth.user?.target_roles||[]); const finishing=ref(false);
async function next(){ if(step.value===0){ const user=await updateUserProfileApi({headline:headline.value,target_roles:targetRoles.value,onboarding_step:'materials'}); auth.user=user; } step.value++; }
async function finish(){ finishing.value=true; try{auth.user=await completeOnboardingApi(); await router.push('/dashboard');}finally{finishing.value=false;} }
</script>
<style scoped>
.onboarding-page{min-height:100vh;background:#f3f6fa}.onboarding-page>header{height:68px;display:flex;align-items:center;justify-content:space-between;padding:0 6vw;background:#fff;border-bottom:1px solid #dfe5ec}.onboarding-page header a{font-size:21px;font-weight:800;color:#172033;text-decoration:none}.onboarding-panel{width:min(820px,calc(100% - 28px));margin:48px auto;padding:28px;background:#fff;border:1px solid #dfe5ec}.step-body{min-height:300px;display:grid;align-content:center;gap:18px}.step-body h1{margin:0;font-size:30px;letter-spacing:0}.step-body p{margin:0;color:#667085}.choice-row{display:flex;gap:12px}.onboarding-panel footer{display:flex;justify-content:flex-end;gap:10px;padding-top:20px;border-top:1px solid #e5e7eb}@media(max-width:640px){.onboarding-panel{margin:18px auto;padding:18px}.choice-row{flex-direction:column}}
</style>
