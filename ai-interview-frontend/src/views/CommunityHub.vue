<template>
  <div class="community-page">
    <nav class="category-nav" aria-label="内容分类">
      <button v-for="category in categories" :key="category.key" :class="{ active: activeCategory === category.key }" :aria-pressed="activeCategory === category.key" @click="activeCategory = category.key; activeTopic = null">
        <el-icon v-if="!category.key"><CollectionTag /></el-icon>{{ category.label }}
      </button>
      <router-link to="/dashboard/blog" class="legacy-link">历史文章</router-link>
      <el-button v-if="statusInfo.configured" link :icon="Link" @click="openCommunity">历史社区</el-button>
    </nav>
    <main class="main-content" aria-label="求职社区内容">
      <header class="content-header">
        <div class="content-tabs" aria-label="内容排序">
          <button :class="{ active: activeTab === 'recommended' }" :aria-pressed="activeTab === 'recommended'" @click="activeTab = 'recommended'">推荐</button>
          <button :class="{ active: activeTab === 'latest' }" :aria-pressed="activeTab === 'latest'" @click="activeTab = 'latest'">最新</button>
        </div>
        <el-button type="primary" :icon="EditPen" @click="createDialog = true">发布内容</el-button>
      </header>
      <form class="search-band" @submit.prevent="search">
        <el-input v-model="query" clearable aria-label="搜索求职社区" placeholder="搜索面经、技术问题和公共知识" @clear="loadFeed"><template #prefix><el-icon><Search /></el-icon></template></el-input>
        <el-button native-type="submit" :loading="loading">搜索</el-button>
        <el-button v-if="searched" link @click="query = ''; loadFeed()">返回内容列表</el-button>
      </form>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon><template #default><el-button link @click="searched ? search() : loadFeed()">重试加载</el-button></template></el-alert>
      <el-alert v-if="searchResult.degraded" title="部分内容来自兼容读取，搜索或原生社区暂时降级" type="warning" show-icon :closable="false" />
      <section v-loading="loading" class="posts-list" aria-live="polite">
        <el-empty v-if="!loading && !loadError && !visibleItems.length" description="这个分类暂时没有内容，试试综合或其他分类" />
        <article v-for="item in visibleItems" :key="`${item.index}-${item.id || item.url}`" class="post-row">
          <div class="card-body">
            <h2><button class="article-title" @click="openItem(item)">{{ item.title || item.name || '未命名内容' }}</button></h2>
            <p class="card-excerpt">{{ excerpt(item) }}</p>
            <div class="card-meta"><span>{{ item.author?.anonymous || item.is_anonymous ? '匿名作者' : item.author?.username || '社区作者' }}</span><span>{{ sourceName(item.index) }}</span><time v-if="item.published_at">{{ formatDate(item.published_at) }}</time><span v-if="item.content_type">{{ typeName(item.content_type) }}</span></div>
          </div>
          <img v-if="item.cover_image" class="card-cover" :src="item.cover_image" alt="内容封面" loading="lazy" />
        </article>
      </section>
      <p v-if="visibleItems.length" class="list-note">当前已加载内容 {{ visibleItems.length }} 条 · 分类与最新排序作用于当前已加载列表</p>
    </main>
    <aside class="right-sidebar" aria-label="推荐阅读与话题">
      <section class="sidebar-module">
        <h2>推荐阅读</h2>
        <ol class="recommended-list"><li v-for="(item, index) in searchResult.results.slice(0, 5)" :key="item.id || item.url"><span :class="{ leading: index < 3 }">{{ index + 1 }}</span><button @click="openItem(item)">{{ item.title || item.name }}</button></li></ol>
        <p v-if="!searchResult.results.length" class="sidebar-empty">暂无公开内容</p>
      </section>
      <section class="sidebar-module">
        <h2>话题</h2>
        <div class="topic-cloud"><button v-for="topic in topics" :key="topic.id" :class="{ selected: activeTopic === topic.id }" :aria-pressed="activeTopic === topic.id" @click="activeTopic = activeTopic === topic.id ? null : topic.id; activeCategory = ''">{{ topic.name }}</button></div>
        <p v-if="!topics.length" class="sidebar-empty">暂无话题</p>
      </section>
      <p class="privacy-note">分享经验，不公开个人隐私。匿名内容仍遵守社区审核规则。</p>
    </aside>
    <el-dialog :model-value="!!selectedItem" :title="selectedItem?.title || selectedItem?.name || '内容详情'" width="min(760px, 94vw)" @close="selectedItem = null">
      <div class="reading-body">{{ selectedItem?.revision?.redacted_body || selectedItem?.content || selectedItem?.excerpt || selectedItem?.summary }}</div>
      <template #footer><el-button @click="selectedItem = null">关闭</el-button></template>
    </el-dialog>
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
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { CollectionTag, EditPen, Link, Search } from '@element-plus/icons-vue';
import { getCommunityFeedApi as getLegacyFeedApi, getCommunityStatusApi, searchCommunityApi, type CommunityStatus } from '@/api/modules/community';
import { createCommunityContentApi, getCommunityFeedApi, getCommunityTopicsApi, publishCommunityContentApi } from '@/api/modules/nativeCommunity';
const router = useRouter(); const query = ref(''); const loading = ref(false); const searched = ref(false); const createDialog = ref(false); const publishing = ref(false);
const form = reactive({ content_type: 'discussion', title: '', body: '', is_anonymous: false });
const statusInfo = reactive<CommunityStatus>({ configured: false, community_url: '', identity: null }); const searchResult = reactive<any>({ results: [], degraded: false, reason: '' });
const categories = [{ key: '', label: '综合' }, { key: 'article', label: '技术文章' }, { key: 'experience', label: '面试经验' }, { key: 'question', label: '技术问答' }, { key: 'resume_clinic', label: '简历诊所' }, { key: 'project_review', label: '项目复盘' }, { key: 'discussion', label: '交流讨论' }];
const activeCategory = ref(''); const activeTab = ref('recommended'); const activeTopic = ref<number | null>(null);
const topics = ref<any[]>([]); const selectedItem = ref<any>(null); const loadError = ref('');
let loadSequence = 0;
const visibleItems = computed(() => {
  const rows = searchResult.results.filter((item: any) => (!activeCategory.value || item.content_type === activeCategory.value) && (activeTopic.value === null || item.topic_ids?.includes(activeTopic.value)));
  return activeTab.value === 'latest' ? [...rows].sort((a: any, b: any) => Date.parse(b.published_at || b.created_at || '') - Date.parse(a.published_at || a.created_at || '')) : rows;
});
function typeName(key: string) { return categories.find(item => item.key === key)?.label || key; }
function excerpt(item: any) { return String(item.excerpt || item.summary || item.content || '').replace(/[#*`>]/g, '').slice(0, 220); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('zh-CN'); }
function openItem(item: any) { if (item.url) openUrl(item.url); else selectedItem.value = item; }
async function loadFeed() {
  const sequence = ++loadSequence;
  loading.value = true;
  searched.value = false; loadError.value = '';
  try {
    try {
      const feed: any = await getCommunityFeedApi();
      const rows = Array.isArray(feed) ? feed : (feed.results || []);
      if (sequence === loadSequence) Object.assign(searchResult, { results: rows.map((item: any) => ({ ...item, index: 'native_community', content: item.revision?.redacted_body })), degraded: false, reason: '' });
    } catch {
      const feed: any = await getLegacyFeedApi();
      if (sequence === loadSequence) Object.assign(searchResult, { results: feed.results || [], degraded: true, reason: 'native_community_shadow_fallback' });
    }
  } catch { if (sequence === loadSequence) loadError.value = '内容加载失败，请稍后重试。'; } finally { if (sequence === loadSequence) loading.value = false; }
}
onMounted(() => {
  loadFeed();
  getCommunityStatusApi().then(status => Object.assign(statusInfo, status)).catch(() => {});
  getCommunityTopicsApi().then((data: any) => { topics.value = Array.isArray(data) ? data : data.results || []; }).catch(() => {});
});
async function search() { if (!query.value.trim()) return loadFeed(); const sequence = ++loadSequence; loading.value = true; searched.value = true; loadError.value = ''; activeCategory.value = ''; activeTopic.value = null; try { const result = await searchCommunityApi(query.value.trim()); if (sequence === loadSequence) Object.assign(searchResult, result); } catch { if (sequence === loadSequence) loadError.value = '搜索失败，请检查网络后重试。'; } finally { if (sequence === loadSequence) loading.value = false; } }
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
  } catch { ElMessage.error('提交失败，请保留正文并稍后重试'); } finally { publishing.value = false; }
}
function openCommunity() { window.open(statusInfo.community_url, '_blank', 'noopener'); }
function openUrl(url: string) { if (url.startsWith('/') && !url.startsWith('//')) router.push(url); else { try { const target = new URL(url); if (['http:', 'https:'].includes(target.protocol)) window.open(target.href, '_blank', 'noopener,noreferrer'); } catch { ElMessage.warning('内容链接无效'); } } }
function sourceName(index: string) { return ({ native_community: '求职社区', community_contents: '求职社区', public_blog: '历史文章', public_knowledge: '公共知识', community_topics: '历史主题' } as Record<string,string>)[index] || index; }
</script>

<style scoped>
.community-page { display: grid; grid-template-columns: minmax(150px, 2fr) minmax(0, 8fr) minmax(230px, 3fr); gap: 20px; align-items: start; min-height: calc(100vh - 60px); padding: 20px 5%; background: #f4f5f5; color: #252933; }
.category-nav, .main-content, .sidebar-module { background: #fff; border-radius: 4px; }
.category-nav { padding: 8px; position: sticky; top: 20px; }
button { font: inherit; cursor: pointer; }
.category-nav > button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 14px 12px; border: 0; border-radius: 4px; background: transparent; color: #252933; text-align: left; }
.category-nav > button:hover, .post-row:hover { background: #fafafa; }
.category-nav > button.active { background: #eaf2ff; color: #1769d2; font-weight: 600; }
.legacy-link { display: block; padding: 16px 12px; border-top: 1px solid #e5e6eb; color: #596273; text-decoration: none; }
.content-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e5e6eb; }
.content-tabs { display: flex; gap: 20px; }
.content-tabs button { border: 0; padding: 8px 0; background: transparent; color: #596273; }
.content-tabs button.active { color: #1769d2; font-weight: 600; }
.search-band { display: flex; gap: 8px; padding: 16px 20px; border-bottom: 1px solid #e5e6eb; }
.posts-list { min-height: 180px; }
.post-row { display: flex; gap: 20px; padding: 24px 20px; border-bottom: 1px solid #e5e6eb; }
.card-body { min-width: 0; flex: 1; }
.post-row h2 { margin: 0 0 10px; font-size: 19px; }
.article-title { border: 0; background: transparent; padding: 0; color: inherit; font-weight: 600; text-align: left; line-height: 1.5; overflow-wrap: anywhere; }
.article-title:hover, .recommended-list button:hover { color: #1769d2; }
.card-excerpt { margin: 0 0 16px; color: #596273; font-size: 14px; line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.card-meta { display: flex; flex-wrap: wrap; gap: 12px; color: #596273; font-size: 13px; }
.card-cover { width: 120px; height: 80px; object-fit: cover; border-radius: 4px; }
.right-sidebar { min-width: 0; }
.sidebar-module { padding: 20px; margin-bottom: 20px; }
.sidebar-module h2 { font-size: 18px; margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid #e5e6eb; }
.recommended-list { list-style: none; padding: 0; margin: 0; }
.recommended-list li { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
.recommended-list li > span { width: 20px; flex-shrink: 0; text-align: center; color: #596273; }
.recommended-list li > span.leading { background: #ffe4bd; color: #854800; }
.recommended-list button { min-width: 0; background: transparent; border: 0; padding: 0; color: #252933; text-align: left; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.topic-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
.topic-cloud button { border: 1px solid #b8d5fa; color: #1769d2; background: white; border-radius: 20px; padding: 6px 10px; font-size: 14px; }
.topic-cloud button.selected { background: #eaf2ff; }
.sidebar-empty, .privacy-note, .list-note { color: #596273; font-size: 13px; line-height: 1.7; }
.list-note { margin: 0; padding: 16px 20px; }
.privacy-note { padding: 0 8px; }
.reading-body { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 16px; line-height: 1.8; }
button:focus-visible, a:focus-visible { outline: 2px solid #1769d2; outline-offset: 3px; }
@media (max-width: 1100px) { .community-page { grid-template-columns: 160px minmax(0, 1fr); padding: 20px; } .right-sidebar { display: none; } }
@media (max-width: 700px) { .community-page { grid-template-columns: 1fr; padding: 12px; gap: 12px; } .category-nav { display: flex; overflow-x: auto; position: static; } .category-nav > button { width: auto; white-space: nowrap; } .legacy-link { white-space: nowrap; border: 0; } .search-band { flex-wrap: wrap; } .search-band :deep(.el-input) { flex: 1 1 180px; } .card-cover { width: 80px; height: 64px; } }
.hint { margin-left: 10px; color: #667085; font-size: 12px; }
</style>
