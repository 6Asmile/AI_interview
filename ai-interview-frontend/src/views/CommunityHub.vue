<template>
  <div class="community-page">
    <header class="page-header">
      <div><h1>求职社区</h1><p>面经、问答、简历诊所和项目复盘统一沉淀；匿名发布仍会保留后台审核链。</p></div>
      <div><el-button @click="router.push('/dashboard/blog')">历史文章</el-button><el-button v-if="statusInfo.configured" :icon="Link" @click="openCommunity">历史社区</el-button><el-button type="primary" @click="createDialog = true">发布内容</el-button></div>
    </header>
    <section class="search-band">
      <el-input v-model="query" size="large" clearable placeholder="搜索面经、技术问题和公共知识" @keyup.enter="search"><template #prefix><el-icon><Search /></el-icon></template></el-input>
      <el-button type="primary" size="large" @click="search">搜索</el-button>
    </section>
    <el-alert v-if="searchResult.degraded" :title="`公开搜索暂时降级：${searchResult.reason}`" type="warning" show-icon :closable="false" />
    <section class="results-section" v-loading="loading">
      <el-empty v-if="!loading && !searchResult.results.length" description="暂时没有公开内容" />
      <article v-for="item in searchResult.results" :key="`${item.index}-${item.id || item.url}`" class="result-row">
        <el-tag size="small" type="info">{{ sourceName(item.index) }}</el-tag>
        <div><h2>{{ item.title || item.name || '未命名内容' }}</h2><p>{{ item.summary || item.excerpt || item.content || '' }}</p></div>
        <el-button v-if="item.url" link type="primary" @click="openUrl(item.url)">查看</el-button>
      </article>
    </section>
    <el-dialog v-model="createDialog" title="发布求职内容" width="min(680px, 94vw)">
      <el-form :model="form" label-width="84px">
        <el-form-item label="类型"><el-select v-model="form.content_type"><el-option label="文章" value="article" /><el-option label="面经" value="experience" /><el-option label="问答" value="question" /><el-option label="简历诊所" value="resume_clinic" /><el-option label="项目复盘" value="project_review" /><el-option label="讨论" value="discussion" /></el-select></el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="240" /></el-form-item>
        <el-form-item label="正文"><el-input v-model="form.body" type="textarea" :rows="9" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item label="匿名"><el-switch v-model="form.is_anonymous" /><span class="hint">前台匿名，后台保留真实作者和审核记录</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="createDialog = false">取消</el-button><el-button type="primary" :loading="publishing" @click="publish">提交审核</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Link, Search } from '@element-plus/icons-vue';
import { getCommunityFeedApi as getLegacyFeedApi, getCommunityStatusApi, searchCommunityApi, type CommunityStatus } from '@/api/modules/community';
import { createCommunityContentApi, getCommunityFeedApi, publishCommunityContentApi } from '@/api/modules/nativeCommunity';
const router = useRouter(); const query = ref(''); const loading = ref(false); const searched = ref(false); const createDialog = ref(false); const publishing = ref(false);
const form = reactive({ content_type: 'discussion', title: '', body: '', is_anonymous: false });
const statusInfo = reactive<CommunityStatus>({ configured: false, community_url: '', identity: null }); const searchResult = reactive<any>({ results: [], degraded: false, reason: '' });
onMounted(async () => {
  loading.value = true;
  try {
    const status: any = await getCommunityStatusApi();
    Object.assign(statusInfo, status);
    try {
      const feed: any = await getCommunityFeedApi();
      const rows = Array.isArray(feed) ? feed : (feed.results || []);
      Object.assign(searchResult, { results: rows.map((item: any) => ({ ...item, index: 'native_community', content: item.revision?.redacted_body })), degraded: false, reason: '' });
    } catch {
      const feed: any = await getLegacyFeedApi();
      Object.assign(searchResult, { results: feed.results || [], degraded: true, reason: 'native_community_shadow_fallback' });
    }
  } finally { loading.value = false; }
});
async function search() { if (!query.value.trim()) return; loading.value = true; searched.value = true; try { Object.assign(searchResult, await searchCommunityApi(query.value.trim())); } finally { loading.value = false; } }
async function publish() {
  if (!form.title.trim() || !form.body.trim()) return ElMessage.warning('请填写标题和正文');
  publishing.value = true;
  try {
    const content: any = await createCommunityContentApi(form);
    const submitted: any = await publishCommunityContentApi(content.id);
    ElMessage.success(submitted.status === 'pending' ? '已进入审核队列' : '发布成功');
    createDialog.value = false;
    Object.assign(form, { content_type: 'discussion', title: '', body: '', is_anonymous: false });
    const feed: any = await getCommunityFeedApi();
    const rows = Array.isArray(feed) ? feed : (feed.results || []);
    searchResult.results = rows.map((item: any) => ({ ...item, index: 'native_community', content: item.revision?.redacted_body }));
  } finally { publishing.value = false; }
}
function openCommunity() { window.open(statusInfo.community_url, '_blank', 'noopener'); }
function openUrl(url: string) { if (url.startsWith('/')) router.push(url); else window.open(url, '_blank', 'noopener'); }
function sourceName(index: string) { return ({ native_community: '求职社区', community_contents: '求职社区', public_blog: '历史文章', public_knowledge: '公共知识', community_topics: '历史主题' } as Record<string,string>)[index] || index; }
</script>

<style scoped>
.community-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }.page-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }.page-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }.page-header p { margin: 8px 0 0; color: #667085; }.search-band { display: grid; grid-template-columns: minmax(0, 720px) auto; gap: 10px; padding: 24px 0; }.results-section { margin-top: 14px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }.result-row { display: grid; grid-template-columns: 90px 1fr 70px; gap: 14px; align-items: start; padding: 18px; border-bottom: 1px solid #edf0f4; }.result-row:last-child { border-bottom: 0; }.result-row h2 { margin: 0; color: #1f2937; font-size: 17px; }.result-row p { margin: 8px 0 0; color: #667085; line-height: 1.6; }@media(max-width:700px){.community-page{padding:14px}.page-header{align-items:flex-start;flex-direction:column}.search-band{grid-template-columns:1fr}.result-row{grid-template-columns:1fr}}
.hint { margin-left: 10px; color: #667085; font-size: 12px; }
</style>
