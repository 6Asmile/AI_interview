<template>
  <main class="about-page">
    <nav><router-link to="/">← IFaceOff</router-link><router-link to="/login">登录</router-link></nav>
    <header><p>ABOUT IFACEOFF</p><h1>让求职准备建立在真实证据上</h1><span>IFaceOff 把职业事实、简历版本、岗位 JD、模拟面试和复盘任务连成一条可追溯的工作流。</span></header>
    <section>
      <article><h2>我们解决什么</h2><p>求职工具常把简历生成、面试问答和评估报告割裂开来。IFaceOff 固定每次使用的简历与 JD 快照，让建议、追问和结论都能回到真实输入。</p></article>
      <article><h2>AI 的边界</h2><p>AI 可以整理、比较和追问，但不能替你编造经历。模型不可用或证据不足时，系统会明确降级，而不是生成看似完整的虚假结论。</p></article>
      <article><h2>隐私与隔离</h2><p>私有简历、私信和个人知识不会进入公共搜索。知识库经过租户校验与人工审批后才可进入面试检索。</p></article>
    </section>
  </main>
</template>
<style scoped>
.about-page { min-height: 100vh; background: #f6f8fb; color: #172033; }.about-page nav { height: 68px; display:flex;justify-content:space-between;align-items:center;padding:0 7vw;background:#fff;border-bottom:1px solid #dfe5ec }.about-page a{color:#1769e0;text-decoration:none}.about-page header{padding:72px 10vw 64px;background:#172033;color:#fff}.about-page header p{font-weight:700}.about-page h1{max-width:820px;margin:10px 0 20px;font-size:52px;letter-spacing:0}.about-page header span{display:block;max-width:760px;color:#d9e3f2;font-size:19px;line-height:1.8}.about-page section{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#dfe5ec;margin:0 7vw}.about-page article{padding:34px;background:#fff}.about-page h2{font-size:21px}.about-page article p{color:#667085;line-height:1.8}@media(max-width:760px){.about-page header{padding:48px 20px}.about-page h1{font-size:36px}.about-page section{grid-template-columns:1fr;margin:0}}
</style>
