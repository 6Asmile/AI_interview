// Real Vue page with synthetic intercepted APIs; not an authenticated backend E2E.
async (page) => {
  const user = { id: 1, username: '合成用户', onboarding_completed_at: '2026-10-07', role: 'user' };
  const contents = [
    { id: 'article-one', title: '从职业事实到可靠的求职平台', content_type: 'article', excerpt: '分享结构化简历、异步任务与工程实践，让每一次修改都有可追溯的依据。', author: { username: '合成作者' }, topic_ids: [1], published_at: '2026-10-06', revision: { redacted_body: '这是合成的公开文章正文。\n不包含私人简历或真实用户数据。' } },
    { id: 'experience-one', title: '一次 AI 应用开发面试的复盘', content_type: 'experience', excerpt: '把面试问题、项目证据和复盘行动串起来。', author: { anonymous: true }, is_anonymous: true, topic_ids: [2], published_at: '2026-10-07', revision: { redacted_body: '这是经过脱敏的合成面经。' } },
    { id: 'review-one', title: '任务重试之后，怎样避免重复业务结果？', content_type: 'project_review', excerpt: '从消息确认、执行租约到并发栅栏，梳理可靠异步链路。', author: { username: '合成工程师' }, topic_ids: [1], published_at: '2026-10-05' },
  ];
  await page.unrouteAll();
  await page.route(/\/api\/v[12]\//, async route => {
    const path = new URL(route.request().url()).pathname;
    let data = { results: [] };
    if (path.endsWith('/auth/session/')) data = { access: 'synthetic-ui-only', user };
    else if (path.endsWith('/auth/profile/')) data = user;
    else if (path.endsWith('/auth/csrf/')) data = { csrf_token: 'synthetic-ui-only' };
    else if (path.endsWith('/community/me/')) data = { configured: false, community_url: '', identity: null };
    else if (path.endsWith('/community/feed/')) data = { results: contents };
    else if (path.endsWith('/community/topics/')) data = { results: [{ id: 1, name: '工程实践' }, { id: 2, name: '面试复盘' }] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto('http://127.0.0.1:5173/dashboard/community');
  await page.getByRole('button', { name: contents[0].title, exact: true }).first().waitFor();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: 'output/playwright/community-restored-desktop.png' });
  await page.getByRole('button', { name: '面试经验', exact: true }).click();
  if (await page.locator('.post-row').count() !== 1) throw new Error('category_filter_failed');
  await page.getByRole('button', { name: '综合', exact: true }).click();
  await page.getByRole('button', { name: '工程实践', exact: true }).click();
  if (await page.locator('.post-row').count() !== 2) throw new Error('topic_filter_failed');
  await page.getByRole('button', { name: contents[0].title, exact: true }).first().click();
  await page.getByRole('dialog').getByText('这是合成的公开文章正文。', { exact: false }).waitFor();
  await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).click();
  await page.getByRole('button', { name: '综合', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'output/playwright/community-restored-mobile.png' });
  const layout = await page.locator('.community-page').evaluate(el => ({ width: el.getBoundingClientRect().width, columns: getComputedStyle(el).gridTemplateColumns }));
  return { scope: 'synthetic_api_real_vue', category_filter: 'passed', topic_filter: 'passed', public_reading: 'passed', mobile_layout: layout };
}
