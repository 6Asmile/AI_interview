import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';


const screenshotDirectory = process.env.IFACEOFF_DOCS_SCREENSHOT_DIR
  ? resolve(process.env.IFACEOFF_DOCS_SCREENSHOT_DIR)
  : resolve(process.cwd(), '../docs/ifaceoff-vault/assets/screenshots');
const adminBaseURL = process.env.IFACEOFF_DOCS_ADMIN_URL || 'http://127.0.0.1:5174';

function screenshotPath(name: string) {
  mkdirSync(screenshotDirectory, { recursive: true });
  return resolve(screenshotDirectory, name);
}

async function capture(
  page: Page,
  route: string,
  filename: string,
  heading?: string | RegExp,
) {
  await page.goto(route);
  if (route.startsWith('/dashboard')) {
    const deferRecovery = page.getByRole('button', { name: '稍后处理' });
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const recoveryPromptAppeared = await deferRecovery
        .waitFor({ state: 'visible', timeout: attempt === 0 ? 10_000 : 3_000 })
        .then(() => true)
        .catch(() => false);
      if (!recoveryPromptAppeared) {
        break;
      }
      await deferRecovery.click();
      await deferRecovery.waitFor({ state: 'hidden' });
    }
  }
  if (heading) {
    await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible({ timeout: 30_000 });
  } else {
    await expect(page.locator('body')).toBeVisible();
  }
  await page.screenshot({ path: screenshotPath(filename), fullPage: false });
}

async function loginCandidate(page: Page) {
  const email = process.env.IFACEOFF_DOCS_EMAIL;
  const password = process.env.IFACEOFF_DOCS_PASSWORD;
  test.skip(
    !email || !password,
    'Set IFACEOFF_DOCS_EMAIL and IFACEOFF_DOCS_PASSWORD to a synthetic documentation account.',
  );
  await page.goto('/login');
  await page.getByPlaceholder('请输入邮箱').fill(email!);
  await page.getByPlaceholder('请输入密码').fill(password!);
  await page.getByRole('button', { name: '登录', exact: true }).last().click();
  const deferRecovery = page.getByRole('button', { name: '稍后处理' });
  const recoveryPromptAppeared = await deferRecovery
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false);
  if (recoveryPromptAppeared) {
    await deferRecovery.click();
  }
  await page.waitForURL(/\/dashboard(?:$|\/)/);
}

async function loginStaff(page: Page) {
  const email = process.env.IFACEOFF_DOCS_STAFF_EMAIL;
  const password = process.env.IFACEOFF_DOCS_STAFF_PASSWORD;
  const mfaCode = process.env.IFACEOFF_DOCS_STAFF_MFA_CODE;
  test.skip(
    !email || !password || !mfaCode,
    'Set staff email, password and the current synthetic MFA code.',
  );
  await page.goto(`${adminBaseURL}/login`);
  const fields = page.locator('.login-form input');
  await fields.nth(0).fill(email!);
  await fields.nth(1).fill(password!);
  await fields.nth(2).fill(mfaCode!);
  await page.getByRole('button', { name: '登录员工端' }).click();
  await page.waitForURL(url => url.origin === new URL(adminBaseURL).origin && url.pathname === '/');
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('capture public product and identity boundaries', async ({ page }) => {
  await capture(page, '/', 'landing-current.png', 'IFaceOff');
  await capture(page, '/about', 'about-current.png', '让求职准备建立在真实证据上');
  await capture(page, '/login', 'candidate-login-current.png');
  await expect(page.getByPlaceholder('请输入邮箱')).toBeVisible();
  await capture(page, '/register', 'candidate-register-current.png');
  await expect(page.getByRole('button', { name: /注册/ }).last()).toBeVisible();
  await capture(page, `${adminBaseURL}/login`, 'staff-login-current.png', '员工登录');
  await expect(page.getByText('候选人账号无法登录此管理端。')).toBeVisible();
});

test('capture candidate implementation pages with synthetic data', async ({ page }) => {
  await loginCandidate(page);

  const resumeId = process.env.IFACEOFF_DOCS_RESUME_ID;
  const activeInterviewId = process.env.IFACEOFF_DOCS_ACTIVE_INTERVIEW_ID;
  const completedInterviewId = process.env.IFACEOFF_DOCS_COMPLETED_INTERVIEW_ID;
  test.skip(
    !resumeId || !activeInterviewId || !completedInterviewId,
    'Set synthetic resume and interview identifiers returned by seed_documentation_demo.',
  );

  const captures = [
    ['/dashboard', '求职概览', 'candidate-dashboard-current.png'],
    ['/dashboard/career', '求职工作台', 'career-workspace-current.png'],
    ['/dashboard/resumes', /把经历整理成可信、可投递的简历/, 'resume-list-current.png'],
    [`/dashboard/resumes/${resumeId}`, 'Resume Studio', 'resume-studio-current.png'],
    ['/dashboard/ai-diagnosis', 'AI 简历诊断', 'resume-diagnosis-current.png'],
    ['/dashboard/interviews', /选择岗位/, 'interview-setup-current.png'],
    [`/dashboard/interview/${activeInterviewId}`, 'AI 面试官', 'interview-room-current.png'],
    [`/dashboard/report/${completedInterviewId}`, 'AI 面试评估报告', 'interview-report-current.png'],
    ['/dashboard/knowledge', '知识库', 'knowledge-current.png'],
    ['/dashboard/community', '求职社区', 'community-current.png'],
    ['/dashboard/chat', /我的私信|私信/, 'chat-current.png'],
    ['/dashboard/tasks', '任务中心', 'task-center-current.png'],
    ['/dashboard/settings', 'AI 模型设置', 'settings-current.png'],
    ['/dashboard/profile', '个人中心', 'profile-current.png'],
  ] as const;
  for (const [route, heading, filename] of captures) {
    await capture(page, route, filename, heading);
  }

  await page.getByRole('button', { name: '打开通知中心' }).click();
  await expect(page.getByRole('heading', { name: '通知中心' })).toBeVisible();
  await page.screenshot({ path: screenshotPath('notification-center-current.png'), fullPage: false });
});

test('capture staff control-plane pages with synthetic data', async ({ page }) => {
  await loginStaff(page);
  const captures = [
    [`${adminBaseURL}/`, '运行概览', 'staff-dashboard-current.png'],
    [`${adminBaseURL}/interview-config`, '模板、量表与评估', 'staff-interview-config-current.png'],
    [`${adminBaseURL}/agent-config`, 'Agent 配置中心', 'staff-agent-config-current.png'],
    [`${adminBaseURL}/knowledge`, '知识审批与块编辑', 'staff-knowledge-current.png'],
    [`${adminBaseURL}/agent-runs`, 'Agent 运行审计', 'staff-agent-runs-current.png'],
    [`${adminBaseURL}/gateway`, '模型网关', 'staff-gateway-current.png'],
    [`${adminBaseURL}/operations`, '任务与系统健康', 'staff-operations-current.png'],
    [`${adminBaseURL}/audit`, '管理审计日志', 'staff-audit-current.png'],
  ] as const;
  for (const [route, heading, filename] of captures) {
    await capture(page, route, filename, heading);
  }
});
