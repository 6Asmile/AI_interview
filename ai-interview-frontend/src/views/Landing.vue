<template>
  <main class="landing-page">
    <nav class="public-nav">
      <router-link class="brand" to="/">IFaceOff</router-link>
      <div>
        <router-link to="/about">关于我们</router-link>
        <router-link to="/login">登录</router-link>
        <router-link class="primary-link" to="/register">开始使用</router-link>
      </div>
    </nav>
    <section class="hero">
      <img src="/hero.webp" alt="IFaceOff AI 模拟面试场景" />
      <div class="hero-overlay"></div>
      <div class="hero-content">
        <p>可信简历 · 自适应面试 · 证据化复盘</p>
        <h1>IFaceOff</h1>
        <span>围绕你的真实经历和目标岗位，完成从简历准备到模拟面试的求职闭环。</span>
        <div class="hero-actions">
          <router-link class="primary-link" to="/register">创建求职档案</router-link>
          <router-link class="secondary-link" to="/login">继续已有进度</router-link>
        </div>
      </div>
    </section>
    <section class="workflow-band">
      <article><strong>01</strong><h2>确认职业事实</h2><p>简历和报告只引用你确认过的教育、项目、经历与成果。</p></article>
      <article><strong>02</strong><h2>匹配真实岗位</h2><p>保存 JD 与投递版本，让每次诊断和面试都可以复现。</p></article>
      <article><strong>03</strong><h2>完成模拟与复盘</h2><p>Agent 根据回答证据动态追问，报告展示覆盖和待补强能力。</p></article>
    </section>
  </main>
</template>

<style scoped>
.landing-page { min-height: 100vh; background: #f4f7fb; color: #172033; }
.public-nav { height: 68px; display: flex; align-items: center; justify-content: space-between; padding: 0 5vw; background: #fff; border-bottom: 1px solid #dfe5ec; }
.public-nav > div { display: flex; align-items: center; gap: 22px; }
.public-nav a { color: #344054; text-decoration: none; }
.brand { font-size: 22px; font-weight: 800; }
.primary-link, .secondary-link { display: inline-flex; align-items: center; justify-content: center; min-height: 42px; padding: 0 18px; text-decoration: none; }
.primary-link { background: #1769e0; color: #fff !important; }
.secondary-link { border: 1px solid rgba(255,255,255,.72); color: #fff; }
.hero { position: relative; height: min(72vh, 720px); min-height: 520px; overflow: hidden; }
.hero > img { width: 100%; height: 100%; object-fit: cover; object-position: center; }
.hero-overlay { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(7,17,35,.88), rgba(7,17,35,.28) 70%, rgba(7,17,35,.08)); }
.hero-content { position: absolute; left: 7vw; top: 50%; width: min(680px, 84vw); transform: translateY(-50%); color: #fff; }
.hero-content p { margin: 0 0 12px; font-weight: 700; }
.hero-content h1 { margin: 0; font-size: 72px; line-height: 1; letter-spacing: 0; }
.hero-content span { display: block; margin-top: 22px; font-size: 20px; line-height: 1.7; }
.hero-actions { display: flex; gap: 12px; margin-top: 30px; }
.workflow-band { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #dfe5ec; border-bottom: 1px solid #dfe5ec; }
.workflow-band article { padding: 30px 5vw; background: #fff; }
.workflow-band strong { color: #1769e0; }.workflow-band h2 { margin: 10px 0; font-size: 20px; }.workflow-band p { margin: 0; color: #667085; line-height: 1.7; }
@media(max-width:760px){.public-nav{padding:0 16px}.public-nav>div{gap:12px}.public-nav>div a:first-child{display:none}.hero{min-height:560px}.hero-content{left:20px}.hero-content h1{font-size:48px}.workflow-band{grid-template-columns:1fr}.hero-actions{flex-direction:column;align-items:flex-start}}
</style>
