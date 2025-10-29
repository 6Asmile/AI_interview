<template>
  <div class="markdown-body" ref="markdownRoot"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { Marked } from 'marked';
// [核心修正] 1. 导入官方的 highlight 扩展
import { markedHighlight } from "marked-highlight";
import hljs from 'highlight.js';
import mermaid from 'mermaid';
import katex from 'katex';

import 'highlight.js/styles/atom-one-dark.css';
import 'katex/dist/katex.min.css';

const props = defineProps<{
  content: string;
}>();

const markdownRoot = ref<HTMLDivElement | null>(null);

// [核心修正] 2. 正确实例化 Marked
const markedInstance = new Marked();

// [核心修正] 3. 使用官方扩展来集成 highlight.js
markedInstance.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code: string, lang: string) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
    return hljs.highlight(code, { language }).value;
  }
}));

// Mermaid 和 KaTeX 的配置保持不变
mermaid.initialize({
  startOnLoad: false,
  theme: 'default' 
});


const renderAll = async () => {
  if (!markdownRoot.value || !props.content) return;

  // 渲染 Markdown
  markdownRoot.value.innerHTML = markedInstance.parse(props.content) as string;

  await nextTick();

  // 渲染 Mermaid
  try {
    const mermaidElements = markdownRoot.value.querySelectorAll('code.language-mermaid');
    const promises = Array.from(mermaidElements).map(async (el, index) => {
      const id = `mermaid-chart-${Date.now()}-${index}`;
      const pre = el.parentElement;
      if (pre) {
        try {
          const { svg } = await mermaid.render(id, el.textContent || '');
          const container = document.createElement('div');
          container.innerHTML = svg;
          container.classList.add('mermaid-container');
          pre.replaceWith(container);
        } catch(e) {
          console.error('Mermaid render error:', e);
          const errorNode = document.createElement('div');
          errorNode.innerText = 'Mermaid diagram failed to render.';
          pre.replaceWith(errorNode);
        }
      }
    });
    await Promise.all(promises);
  } catch (error) {
    console.error('Error processing Mermaid elements:', error);
  }
  
  // 渲染 KaTeX
  try {
     const katexElements = markdownRoot.value.querySelectorAll('code.language-katex');
      katexElements.forEach(el => {
        const pre = el.parentElement;
        if (pre) {
          try {
            const html = katex.renderToString(el.textContent || '', {
              throwOnError: false,
              displayMode: true
            });
            const container = document.createElement('div');
            container.innerHTML = html;
            pre.replaceWith(container);
          } catch(e) {
            console.error('KaTeX render error:', e);
            const errorNode = document.createElement('div');
            errorNode.innerText = 'KaTeX formula failed to render.';
            pre.replaceWith(errorNode);
          }
        }
      });
  } catch (error) {
     console.error('Error processing KaTeX elements:', error);
  }
};

onMounted(renderAll);
watch(() => props.content, renderAll);

</script>

<style>
/* ... 样式部分保持不变 ... */
.markdown-body { line-height: 1.75; font-size: 16px; }
.markdown-body h1, .markdown-body h2, .markdown-body h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; margin-top: 24px; margin-bottom: 16px; font-weight: 600; }
.markdown-body h1 { font-size: 2em; }
.markdown-body h2 { font-size: 1.5em; }
.markdown-body h3 { font-size: 1.25em; }
.markdown-body p { margin-bottom: 16px; }
.markdown-body blockquote { padding: 0 1em; color: #6a737d; border-left: .25em solid #dfe2e5; margin-bottom: 16px; }
.markdown-body ul, .markdown-body ol { padding-left: 2em; margin-bottom: 16px; }
.markdown-body code { padding: .2em .4em; margin: 0; font-size: 85%; background-color: rgba(27,31,35,.05); border-radius: 3px; }
.markdown-body pre { word-break: break-all; white-space: pre-wrap; background-color: #282c34; border-radius: 6px; padding: 16px; margin-bottom: 16px; overflow: auto; }
.markdown-body pre code { padding: 0; margin: 0; font-size: inherit; background: transparent; }
.markdown-body table { display: block; width: 100%; overflow: auto; border-collapse: collapse; margin-bottom: 16px; }
.markdown-body tr { background-color: #fff; border-top: 1px solid #c6cbd1; }
.markdown-body th, .markdown-body td { padding: 6px 13px; border: 1px solid #dfe2e5; }
.markdown-body .mermaid-container { text-align: center; margin-bottom: 16px; }
</style>