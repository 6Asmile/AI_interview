<template>
  <div class="home-page">
    <section class="hero-section">
      <div class="hero-copy">
        <p class="eyebrow">AI Mock Interview Platform</p>
        <h1>用更接近真实企业面试的方式，训练你的表达、项目复盘和岗位匹配能力</h1>
        <p class="hero-description">
          IFaceOff 会根据岗位、JD、简历和你的实时回答动态追问，帮助你发现回答中的空泛点、能力证据缺口和未验证风险。
        </p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="router.push({ name: 'InterviewSetup' })">开始模拟面试</el-button>
          <el-button size="large" plain @click="router.push({ name: 'ResumeManagement' })">完善我的简历</el-button>
        </div>
      </div>
      <div class="hero-visual">
        <img src="/hero.webp" alt="AI 模拟面试平台展示" />
      </div>
    </section>

    <section class="feature-section">
      <div class="section-heading">
        <p class="eyebrow">Platform Capabilities</p>
        <h2>项目核心功能</h2>
      </div>
      <div class="feature-grid">
        <div v-for="feature in features" :key="feature.title" class="feature-card">
          <span>{{ feature.index }}</span>
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.description }}</p>
        </div>
      </div>
    </section>

    <section class="workflow-section">
      <div class="workflow-copy">
        <p class="eyebrow">Interview Flow</p>
        <h2>从准备到复盘的完整链路</h2>
        <p>先确认岗位和 JD，再进入面试房间答题。系统会根据每轮回答质量生成下一题，结束后沉淀成可复盘的报告。</p>
      </div>
      <div class="workflow-steps">
        <div v-for="step in steps" :key="step.title" class="workflow-step">
          <strong>{{ step.title }}</strong>
          <p>{{ step.description }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { ElButton } from 'element-plus';

const router = useRouter();

const features = [
  { index: '01', title: '岗位与 JD 驱动提问', description: '支持产品、开发、AI 应用、游戏客户端等不同岗位，结合真实 JD 动态生成面试策略。' },
  { index: '02', title: '面试 Agent 动态追问', description: '根据回答质量、追问目标和短期记忆决定下一题，不再是固定题库式问答。' },
  { index: '03', title: '结构化回答点评', description: '从清晰度、深度、相关性、证据质量等维度评分，并解释为什么要继续追问。' },
  { index: '04', title: '录像与历史回放', description: '支持面试录像上传、原始录像 fallback 和后台压缩状态展示，方便复盘表达表现。' },
  { index: '05', title: '简历中心与 AI 诊断', description: '管理在线简历，结合岗位 JD 做简历匹配分析和优化建议。' },
  { index: '06', title: '面试报告验证链路', description: '报告会映射每题质量分、已验证能力和未验证风险，而不是只给泛泛总结。' },
];

const steps = [
  { title: '配置面试', description: '选择岗位、简历、题量、是否录像，并粘贴真实 JD。' },
  { title: '进入房间', description: 'AI 面试官先引导自我介绍，再按简历和回答逐步追问。' },
  { title: '提交回答', description: '系统即时评估质量，并给出下一题追问方向。' },
  { title: '生成报告', description: '面试结束后输出能力评分、改进建议和验证链路。' },
];
</script>

<style scoped>
.home-page {
  min-height: calc(100vh - 60px);
  padding: 28px;
  background:
    radial-gradient(circle at 12% 8%, rgba(76, 146, 255, 0.16), transparent 28%),
    radial-gradient(circle at 88% 4%, rgba(45, 205, 175, 0.14), transparent 25%),
    linear-gradient(180deg, #f7faff 0%, #eef4fb 100%);
}

.hero-section,
.feature-section,
.workflow-section {
  max-width: 1480px;
  margin: 0 auto 26px;
  border: 1px solid rgba(201, 214, 236, 0.78);
  border-radius: 32px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 24px 60px rgba(47, 74, 119, 0.09);
  backdrop-filter: blur(14px);
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(420px, 1.08fr);
  gap: 28px;
  align-items: center;
  padding: 34px;
}

.eyebrow {
  margin: 0 0 10px;
  color: #5d7bb0;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero-copy h1,
.section-heading h2,
.workflow-copy h2 {
  margin: 0;
  color: #1c2d4b;
  line-height: 1.16;
}

.hero-copy h1 {
  max-width: 760px;
  font-size: clamp(34px, 3.3vw, 58px);
}

.hero-description {
  max-width: 680px;
  margin: 22px 0 0;
  color: #60708f;
  font-size: 17px;
  line-height: 1.85;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 28px;
}

.hero-actions :deep(.el-button) {
  min-height: 48px;
  border-radius: 16px;
}

.hero-visual {
  overflow: hidden;
  border: 1px solid rgba(196, 213, 239, 0.9);
  border-radius: 28px;
  background: linear-gradient(135deg, #eef6ff 0%, #ffffff 100%);
  box-shadow: 0 24px 52px rgba(46, 86, 153, 0.13);
}

.hero-visual img {
  display: block;
  width: 100%;
  min-height: 360px;
  object-fit: cover;
}

.feature-section,
.workflow-section {
  padding: 28px;
}

.section-heading {
  margin-bottom: 20px;
}

.section-heading h2,
.workflow-copy h2 {
  font-size: 30px;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.feature-card {
  min-height: 172px;
  padding: 22px;
  border: 1px solid #e1eafa;
  border-radius: 24px;
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
}

.feature-card span {
  color: #2e6bd9;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.feature-card h3 {
  margin: 14px 0 9px;
  color: #1d3150;
  font-size: 19px;
}

.feature-card p,
.workflow-copy p,
.workflow-step p {
  margin: 0;
  color: #667792;
  line-height: 1.75;
}

.workflow-section {
  display: grid;
  grid-template-columns: 0.8fr 1.2fr;
  gap: 24px;
  align-items: center;
}

.workflow-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.workflow-step {
  padding: 18px;
  border: 1px solid #dce8fb;
  border-radius: 22px;
  background: #f8fbff;
}

.workflow-step strong {
  display: block;
  margin-bottom: 8px;
  color: #234169;
}

@media (max-width: 1100px) {
  .hero-section,
  .workflow-section {
    grid-template-columns: 1fr;
  }

  .feature-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .home-page {
    padding: 16px;
  }

  .hero-section,
  .feature-section,
  .workflow-section {
    padding: 20px;
    border-radius: 24px;
  }

  .feature-grid,
  .workflow-steps {
    grid-template-columns: 1fr;
  }
}
</style>
