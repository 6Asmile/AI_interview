<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { Lock } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { getPublicResumeShareApi, type JsonResume, type ResumeDesign } from '@/api/modules/resume';

const route = useRoute();
const token = String(route.params.token || '');
const loading = ref(true);
const password = ref('');
const passwordRequired = ref(false);
const data = ref<{ title: string; version: number; resume_json: JsonResume; design: ResumeDesign; allow_download: boolean } | null>(null);
const basics = computed(() => data.value?.resume_json.basics || {});

async function load() {
  loading.value = true;
  try {
    data.value = await getPublicResumeShareApi(token, password.value);
    passwordRequired.value = false;
  } catch (error: any) {
    if (error?.response?.status === 401) passwordRequired.value = true;
  } finally {
    loading.value = false;
  }
}

async function unlock() {
  if (!password.value) {
    ElMessage.warning('请输入分享密码');
    return;
  }
  await load();
}

onMounted(load);
</script>

<template>
  <main class="share-page" v-loading="loading">
    <section v-if="passwordRequired" class="unlock-card">
      <el-icon><Lock /></el-icon>
      <h1>这份简历受密码保护</h1>
      <el-input v-model="password" type="password" show-password placeholder="访问密码" @keyup.enter="unlock" />
      <el-button type="primary" @click="unlock">查看简历</el-button>
    </section>
    <article v-else-if="data" class="resume-paper">
      <header>
        <div>
          <h1>{{ basics.name || data.title }}</h1>
          <p>{{ basics.label }}</p>
        </div>
        <small>共享快照 v{{ data.version }}</small>
      </header>
      <div class="contact">{{ [basics.email, basics.phone, basics.location?.city, basics.url].filter(Boolean).join(' · ') }}</div>
      <section v-if="basics.summary"><h2>职业摘要</h2><p>{{ basics.summary }}</p></section>
      <section v-if="data.resume_json.work.length">
        <h2>工作经历</h2>
        <div v-for="item in data.resume_json.work" :key="item['x-ifaceoff']?.id || item.name" class="entry">
          <div><strong>{{ item.name }}</strong><span>{{ item.startDate }} — {{ item.endDate || '至今' }}</span></div>
          <b>{{ item.position }}</b><p>{{ item.summary }}</p>
          <ul v-if="item.highlights?.length"><li v-for="line in item.highlights" :key="line">{{ line }}</li></ul>
        </div>
      </section>
      <section v-if="data.resume_json.projects.length">
        <h2>项目经历</h2>
        <div v-for="item in data.resume_json.projects" :key="item['x-ifaceoff']?.id || item.name" class="entry">
          <div><strong>{{ item.name }}</strong><span>{{ item.startDate }} — {{ item.endDate }}</span></div>
          <p>{{ item.description }}</p><small>{{ (item.keywords || []).join(' · ') }}</small>
        </div>
      </section>
      <section v-if="data.resume_json.education.length">
        <h2>教育经历</h2>
        <div v-for="item in data.resume_json.education" :key="item['x-ifaceoff']?.id || item.institution" class="entry">
          <div><strong>{{ item.institution }}</strong><span>{{ item.startDate }} — {{ item.endDate }}</span></div>
          <p>{{ item.studyType }} · {{ item.area }}</p>
        </div>
      </section>
      <section v-if="data.resume_json.skills.length"><h2>专业技能</h2><p v-for="item in data.resume_json.skills" :key="item.name"><strong>{{ item.name }}：</strong>{{ (item.keywords || []).join('、') }}</p></section>
    </article>
  </main>
</template>

<style scoped>
.share-page { min-height: 100vh; padding: 42px 18px; color: #172033; background: #e9edf2; }
.unlock-card { display: grid; width: min(420px, 92vw); gap: 18px; margin: 12vh auto; padding: 34px; border-radius: 18px; background: #fff; box-shadow: 0 20px 60px rgba(15,23,42,.12); text-align: center; }
.unlock-card .el-icon { justify-self: center; color: #0f766e; font-size: 36px; }
.unlock-card h1 { margin: 0; }
.resume-paper { width: min(820px, 100%); min-height: 1120px; margin: 0 auto; padding: clamp(30px, 7vw, 68px); background: #fff; box-shadow: 0 20px 60px rgba(15,23,42,.15); }
.resume-paper > header, .entry > div { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; }
.resume-paper h1 { margin: 0; font-size: 34px; }
.resume-paper header p { margin: 6px 0 0; color: #475467; }
.resume-paper header small, .entry span, .entry small { color: #667085; }
.contact { margin: 18px 0 30px; padding-bottom: 16px; border-bottom: 2px solid #0f766e; color: #475467; }
.resume-paper section { margin-top: 26px; }
.resume-paper h2 { margin: 0 0 14px; color: #0f766e; font-size: 17px; text-transform: uppercase; letter-spacing: .05em; }
.entry { margin-top: 16px; }
.entry p { margin: 6px 0; line-height: 1.6; }
.entry ul { margin: 8px 0; padding-left: 20px; }
@media (max-width: 600px) {
  .share-page { padding: 0; }
  .resume-paper { min-height: 100vh; box-shadow: none; }
  .resume-paper > header, .entry > div { align-items: flex-start; flex-direction: column; gap: 4px; }
}
</style>
