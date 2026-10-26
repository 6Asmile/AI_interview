// Playwright CLI run-code setup: real built UI, synthetic intercepted API only.
async (page) => {
  await page.route('**/api/admin/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    let data = {};
    if (url.pathname.endsWith('/auth/session/')) {
      data = { account: { id: 'synthetic', display_name: '合成队列管理员', email: 'synthetic@example.test', permissions: ['*'], roles: [] } };
    } else if (url.pathname.endsWith('/operations/events/')) {
      data = { database_outbox: {}, consumer_inbox: {}, operations: {}, operation_dispatch: {},
        broker_dead_letters: { queues: ['ifaceoff.v2.resume.render.dlq'], status: 'implemented-partial',
          message: '合成 API 数据，仅验证当前真实页面交互，不代表真实 Broker 页面闭环。' } };
    } else if (url.pathname.endsWith('/operations/broker-dlq/')) {
      if (request.method() === 'GET') data = { ready: 2, consumers: 0 };
      else {
        const body = request.postDataJSON();
        data = { dry_run: body.dry_run, examined: 2, replayed: body.dry_run ? 0 : 1,
          retained: body.dry_run ? 2 : 1, complete: true,
          messages: [{ body_hash: 'synthetic-checksum-only', status: body.dry_run ? 'eligible' : 'replayed', routing_key: 'resume.render' },
            { body_hash: 'synthetic-legacy-checksum', status: 'retained', code: 'unsupported_durable_task' }] };
      }
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto('http://127.0.0.1:4179/operations/events');
}
