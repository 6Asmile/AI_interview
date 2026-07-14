import { expect, test, type Page } from '@playwright/test';

function collectRuntimeFailures(page: Page) {
  const failures: string[] = [];
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`));
  page.on('response', response => {
    if (/\/api\/(v1|v2)\//.test(response.url()) && response.status() >= 400) {
      failures.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  return failures;
}

test('public pages and authenticated critical flows render without runtime failures', async ({ page, context }) => {
  const email = process.env.IFACEOFF_E2E_EMAIL;
  const password = process.env.IFACEOFF_E2E_PASSWORD;
  test.skip(!email || !password, 'Set IFACEOFF_E2E_EMAIL and IFACEOFF_E2E_PASSWORD.');
  const failures = collectRuntimeFailures(page);

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'IFaceOff', exact: true })).toBeVisible();
  await page.goto('/about');
  await expect(page.getByRole('heading', { name: '让求职准备建立在真实证据上' })).toBeVisible();

  await page.goto('/login');
  await page.getByPlaceholder('请输入邮箱').fill(email!);
  await page.getByPlaceholder('请输入密码').fill(password!);
  await page.getByRole('button', { name: '登录', exact: true }).last().click();
  await page.waitForURL(/\/dashboard(?:$|\/)/);

  await page.goto('/dashboard/career');
  await expect(page.getByRole('heading', { name: '求职工作台' })).toBeVisible();
  await expect(page.locator('.career-page')).toBeVisible();

  await page.goto('/dashboard/community');
  await expect(page.getByRole('heading', { name: '技术社区' })).toBeVisible();
  await expect(page.locator('.result-row').first()).toBeVisible();

  await page.goto('/dashboard/knowledge');
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible();
  await expect(page.locator('.el-table__row').first()).toBeVisible();
  const editChunks = page.getByRole('button', { name: '编辑块' });
  if (await editChunks.count()) {
    await editChunks.first().click();
    await expect(page.getByText('解析后知识块编辑')).toBeVisible();
    await expect(page.locator('.chunk-editor-item').first()).toBeVisible();
  }

  await page.goto('/dashboard/ai-diagnosis');
  await expect(page.getByRole('heading', { name: /简历.*诊断/ })).toBeVisible();

  await page.goto('/dashboard/chat');
  await expect(page.getByRole('heading', { name: '我的私信' })).toBeVisible();
  const conversations = page.locator('.conversation-item');
  if (await conversations.count()) {
    await conversations.first().click();
    const composer = page.locator('.composer-input textarea');
    await expect(composer).toBeVisible();
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.evaluate(() => navigator.clipboard.writeText('Playwright 粘贴验证'));
    await composer.focus();
    await page.keyboard.press('Control+V');
    await expect(composer).toHaveValue('Playwright 粘贴验证');
    await page.keyboard.press('Shift+Enter');
    await expect(composer).toHaveValue('Playwright 粘贴验证\n');
    await page.getByRole('button', { name: '选择表情' }).click();
    await expect(page.getByText('常用表情')).toBeVisible();
  }

  expect(failures, failures.join('\n')).toEqual([]);
});

test('admin login remains an independent Django session entry', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '管理端登录' }).click();
  await page.waitForURL(/127\.0\.0\.1:8000\/admin\/login/);
  await expect(page.locator('form')).toBeVisible();
});
