<template>
  <div class="community-page">
    <header class="page-header">
      <div><h1>技术社区</h1><p>搜索公开文章、公共知识和社区主题；简历、私信与私人知识不会进入公开索引。</p></div>
      <div><el-button @click="router.push('/dashboard/blog')">精选文章</el-button><el-button v-if="statusInfo.configured" type="primary" :icon="Link" @click="openCommunity">进入讨论社区</el-button></div>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Link, Search } from '@element-plus/icons-vue';
import { getCommunityFeedApi, getCommunityStatusApi, searchCommunityApi, type CommunityStatus } from '@/api/modules/community';
const router = useRouter(); const query = ref(''); const loading = ref(false); const searched = ref(false); const statusInfo = reactive<CommunityStatus>({ configured: false, community_url: '', identity: null }); const searchResult = reactive<any>({ results: [], degraded: false, reason: '' });
onMounted(async () => {
  loading.value = true;
  try {
    const [status, feed]: any[] = await Promise.all([getCommunityStatusApi(), getCommunityFeedApi()]);
    Object.assign(statusInfo, status);
    Object.assign(searchResult, { results: feed.results || [], degraded: false, reason: '' });
  } finally { loading.value = false; }
});
async function search() { if (!query.value.trim()) return; loading.value = true; searched.value = true; try { Object.assign(searchResult, await searchCommunityApi(query.value.trim())); } finally { loading.value = false; } }
function openCommunity() { window.open(statusInfo.community_url, '_blank', 'noopener'); }
function openUrl(url: string) { if (url.startsWith('/')) router.push(url); else window.open(url, '_blank', 'noopener'); }
function sourceName(index: string) { return ({ public_blog: '精选文章', public_knowledge: '公共知识', community_topics: '社区主题' } as Record<string,string>)[index] || index; }
</script>

<style scoped>
.community-page { min-height: calc(100vh - 60px); padding: 24px; background: #f5f7fa; }.page-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ec; }.page-header h1 { margin: 0; color: #1f2937; font-size: 28px; letter-spacing: 0; }.page-header p { margin: 8px 0 0; color: #667085; }.search-band { display: grid; grid-template-columns: minmax(0, 720px) auto; gap: 10px; padding: 24px 0; }.results-section { margin-top: 14px; background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; }.result-row { display: grid; grid-template-columns: 90px 1fr 70px; gap: 14px; align-items: start; padding: 18px; border-bottom: 1px solid #edf0f4; }.result-row:last-child { border-bottom: 0; }.result-row h2 { margin: 0; color: #1f2937; font-size: 17px; }.result-row p { margin: 8px 0 0; color: #667085; line-height: 1.6; }@media(max-width:700px){.community-page{padding:14px}.page-header{align-items:flex-start;flex-direction:column}.search-band{grid-template-columns:1fr}.result-row{grid-template-columns:1fr}}
</style>
