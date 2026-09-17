import { expect, test } from '@playwright/test';

test('resume imports use the v2 API base without nesting under v1', async ({ page }) => {
  let requestUrl = '';
  await page.route('**/resume-imports/', async route => {
    requestUrl = route.request().url();
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        operation_id: '00000000-0000-0000-0000-000000000000',
        status: 'accepted',
        events_url: '/api/v2/operations/00000000-0000-0000-0000-000000000000/events/',
        result_url: '/api/v2/operations/00000000-0000-0000-0000-000000000000/',
      }),
    });
  });

  await page.goto('/');
  await page.evaluate(async () => {
    const { importResumeV2Api } = await import('/src/api/modules/resume.ts');
    const form = new FormData();
    form.append('file', new File(['resume'], 'resume.pdf', { type: 'application/pdf' }));
    await importResumeV2Api(form);
  });

  expect(new URL(requestUrl).pathname).toBe('/api/v2/resume-imports/');
});
