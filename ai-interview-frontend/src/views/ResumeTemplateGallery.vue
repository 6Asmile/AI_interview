<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Check } from '@element-plus/icons-vue';
import { getResumeTemplatesApi, type ResumeTemplate } from '@/api/modules/resume';

const route = useRoute();
const router = useRouter();
const templates = ref<ResumeTemplate[]>([]);
const selected = ref<ResumeTemplate | null>(null);
const filterType = ref<'all' | 'use' | 'industry' | 'role'>('all');
const filterValue = ref('');
const filterOptions = computed(() => {
  const key = filterType.value === 'use' ? 'use_tags' : filterType.value === 'industry' ? 'industry_tags' : 'role_tags';
  return filterType.value === 'all' ? [] : [...new Set(templates.value.flatMap(template => template[key] || []))];
});
const visibleTemplates = computed(() => {
  if (filterType.value === 'all' || !filterValue.value) return templates.value;
  const key = filterType.value === 'use' ? 'use_tags' : filterType.value === 'industry' ? 'industry_tags' : 'role_tags';
  return templates.value.filter(template => template[key]?.includes(filterValue.value));
});
function useTemplate(template: ResumeTemplate) {
  const resumeId = Number(route.query.resume);
  router.push(Number.isInteger(resumeId) && resumeId > 0
    ? { path: `/dashboard/resumes/${resumeId}`, query: { template: template.key } }
    : { path: '/dashboard/resumes', query: { template: template.key } });
}
onMounted(async () => { templates.value = (await getResumeTemplatesApi()).templates; selected.value = templates.value[0] || null; });
</script>

<template>
  <div class="template-gallery">
    <header class="gallery-header"><el-button circle text :icon="ArrowLeft" aria-label="返回" @click="router.back()" /><div><h1>简历模板中心</h1><p>六套经过固定渲染器验证的单栏母版，按用途、行业和岗位快速筛选。</p></div></header>
    <section class="gallery-filter" aria-label="模板筛选"><el-segmented v-model="filterType" :options="[{label:'全部',value:'all'},{label:'用途',value:'use'},{label:'行业',value:'industry'},{label:'职业',value:'role'}]" @change="filterValue = ''" /><el-select v-if="filterType !== 'all'" v-model="filterValue" clearable placeholder="选择筛选条件"><el-option v-for="option in filterOptions" :key="option" :label="option" :value="option" /></el-select><span>{{ visibleTemplates.length }} 套可用母版</span></section>
    <div class="gallery-layout"><div class="gallery-list"><button v-for="template in visibleTemplates" :key="template.key" type="button" :class="{ active: selected?.key === template.key }" @click="selected = template"><img :src="template.thumbnail" :alt="`${template.name['zh-CN']} 模板缩略图`" /><span><strong>{{ template.name['zh-CN'] }}</strong><small>{{ template.description }}</small></span></button></div><article v-if="selected" class="template-preview"><div class="preview-sheet"><img :src="selected.thumbnail" :alt="`${selected.name['zh-CN']} 模板大图预览`" /></div><div class="preview-copy"><h2>{{ selected.name['zh-CN'] }}</h2><p>{{ selected.description }}</p><dl><div><dt>适合用途</dt><dd><el-tag v-for="tag in selected.use_tags" :key="tag" effect="plain">{{ tag }}</el-tag></dd></div><div><dt>行业</dt><dd><el-tag v-for="tag in selected.industry_tags" :key="tag" effect="plain">{{ tag }}</el-tag></dd></div><div><dt>岗位</dt><dd><el-tag v-for="tag in selected.role_tags" :key="tag" effect="plain">{{ tag }}</el-tag></dd></div></dl><ul><li><el-icon><Check /></el-icon>A4 与 Letter</li><li><el-icon><Check /></el-icon>中英文双语</li><li><el-icon><Check /></el-icon>PDF 与预览同源</li><li><el-icon><Check /></el-icon>可选择文本与嵌入字体</li></ul><el-button type="primary" size="large" @click="useTemplate(selected)">在 Resume Studio 中使用</el-button></div></article></div>
  </div>
</template>

<style scoped>
.template-gallery{min-height:100%;padding:28px clamp(18px,4vw,56px) 64px;color:#18212f;background:#eef1f4}.gallery-header{display:flex;align-items:flex-start;gap:14px}.gallery-header h1{margin:0;font-size:30px;letter-spacing:-.03em}.gallery-header p{max-width:65ch;margin:8px 0 0;color:#59677b}.gallery-filter{display:flex;align-items:center;gap:14px;margin:26px 0;padding:14px 16px;border:1px solid #d7dde5;border-radius:12px;background:#fff}.gallery-filter .el-select{width:220px}.gallery-filter>span{margin-left:auto;color:#637085;font-size:13px}.gallery-layout{display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:24px}.gallery-list{display:grid;gap:10px;align-content:start}.gallery-list button{display:grid;grid-template-columns:120px 1fr;gap:14px;overflow:hidden;padding:0;border:1px solid #d6dde6;border-radius:12px;color:inherit;background:#fff;cursor:pointer;text-align:left}.gallery-list button.active{border-color:#2d6ac5;box-shadow:0 0 0 2px rgba(45,106,197,.12)}.gallery-list img{width:120px;height:90px;object-fit:cover}.gallery-list span{padding:14px 12px 10px 0}.gallery-list strong,.gallery-list small{display:block}.gallery-list small{margin-top:7px;color:#657287;line-height:1.45}.template-preview{display:grid;grid-template-columns:minmax(320px,1fr) minmax(260px,360px);gap:30px;padding:26px;border:1px solid #d4dbe4;border-radius:14px;background:#fff}.preview-sheet{display:grid;min-height:580px;padding:34px;background:#d9dee3;place-items:center}.preview-sheet img{width:min(100%,560px);box-shadow:0 18px 42px rgba(24,33,47,.2)}.preview-copy h2{margin:0;font-size:25px}.preview-copy p{color:#59677b;line-height:1.65}.preview-copy dl{display:grid;gap:15px;margin:24px 0}.preview-copy dt{margin-bottom:7px;color:#48566b;font-size:12px;font-weight:700}.preview-copy dd{display:flex;flex-wrap:wrap;gap:6px;margin:0}.preview-copy ul{display:grid;gap:9px;margin:24px 0;padding:0;list-style:none}.preview-copy li{display:flex;align-items:center;gap:8px;color:#3d4b60}.preview-copy li .el-icon{color:#238256}@media(max-width:1050px){.gallery-layout,.template-preview{grid-template-columns:1fr}.gallery-list{grid-template-columns:repeat(2,minmax(0,1fr))}.preview-sheet{min-height:420px}}@media(max-width:680px){.template-gallery{padding:18px 14px 48px}.gallery-filter{align-items:stretch;flex-direction:column}.gallery-filter .el-select{width:100%}.gallery-filter>span{margin-left:0}.gallery-list{grid-template-columns:1fr}.template-preview{padding:14px}.preview-sheet{min-height:300px;padding:18px}}
</style>
