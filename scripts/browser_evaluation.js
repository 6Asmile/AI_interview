async (page) => {
  const fixture = __FIXTURE__;
  const rows = [];
  const authStatuses = [];
  const artifacts = new Map();
  let savedDraft = null;
  const networkTimings = [];
  const pendingRequests = new Map();
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.includes('/api/v2/')) pendingRequests.set(request, { path, method: request.method(), started: Date.now() });
  });
  page.on('response', async response => {
    const requestTiming = pendingRequests.get(response.request());
    if (requestTiming) {
      networkTimings.push({ ...requestTiming, ended: Date.now(), status: response.status() });
      pendingRequests.delete(response.request());
    }
    if (response.url().endsWith('/draft/') && response.request().method() === 'PATCH' && response.status() === 200) {
      savedDraft = await response.json().catch(() => null);
    }
    if (response.url().includes('/resume-artifacts/') && response.status() === 200) {
      const data = await response.json().catch(() => null);
      if (data?.id) artifacts.set(data.id, data);
    }
  });
  page.on('response', response => {
    if (response.url().includes('/auth/login/')) authStatuses.push(response.status());
  });
  const login = async () => {
    await page.goto('http://127.0.0.1:5173/login');
    await page.getByRole('textbox', { name: '邮箱' }).fill(fixture.email);
    await page.getByRole('textbox', { name: '密码' }).fill(fixture.password);
    await page.getByRole('button', { name: '登录', exact: true }).click();
    // A precreated running fixture intentionally exercises the unfinished-session prompt.
    const later = page.getByRole('button', { name: '稍后处理', exact: true });
    await later.waitFor({ timeout: 5000 }).then(() => later.click()).catch(() => {});
    await page.waitForURL(url => url.pathname.startsWith('/dashboard'), { timeout: 15000 });
  };
  try {
  await login();
  await page.reload();
  await page.waitForTimeout(1500);
  rows.push({ name: '浏览器刷新恢复登录', status: page.url().includes('/login') ? 'failed' : 'passed' });
  if (page.url().includes('/login')) await login();
  const secondTab = await page.context().newPage();
  await secondTab.goto('http://127.0.0.1:5173/dashboard/resumes/' + fixture.resume_id);
  await secondTab.getByRole('textbox', { name: '职业摘要', exact: true }).waitFor({ timeout: 15000 });
  rows.push({ name: '新标签恢复登录', status: secondTab.url().includes('/login') ? 'failed' : 'passed' });
  await secondTab.close();
  // SPA navigation via real sidebar, avoiding the known full-reload auth defect.
  await page.evaluate(resumeId => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/dashboard/resumes/' + resumeId), fixture.resume_id);
  const field = page.getByRole('textbox', { name: '职业摘要', exact: true });
  const firstText = '合成自动保存首稿 ' + Date.now();
  const finalText = '合成自动保存最终稿 ' + Date.now();
  let delayedFirstSave = false;
  await page.route('**/api/v2/resumes/*/draft/', async route => {
    if (!delayedFirstSave) {
      delayedFirstSave = true;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    await route.continue();
  });
  await field.fill(firstText);
  await page.waitForTimeout(850); // 首次 PATCH 已发出并被人为延迟
  const finalEditStarted = Date.now();
  await field.fill(finalText); // 期间继续输入，旧响应不能覆盖这次编辑
  await page.waitForFunction(() => document.querySelector('.studio-toolbar__identity p')?.textContent?.includes('草稿与预览已同步'), null, { timeout: 10000 });
  const saveVisibleMs = Date.now() - finalEditStarted;
  await page.waitForTimeout(1500);
  const saveFailed = await page.getByText('保存失败', { exact: false }).count();
  rows.push({ name: 'Studio 连续编辑与自动保存', status: saveFailed || !delayedFirstSave ? 'failed' : 'pending-verification', expected_summary: finalText,
    delayed_inflight_edit: delayedFirstSave, final_edit_to_saved_indicator_ms: saveVisibleMs });
  if (fixture.resume_only && !saveFailed) {
    const preview = page.getByRole('img', { name: '简历服务端权威预览', exact: true });
    try {
      const deadline = Date.now() + 65000;
      let latestPreview;
      while (Date.now() < deadline) {
        latestPreview = [...artifacts.values()].find(item => item.format === 'preview' && item.status === 'ready' &&
          savedDraft?.resume_json?.basics?.summary === finalText && item.draft_etag === savedDraft.etag);
        if (latestPreview) break;
        await page.waitForTimeout(200);
      }
      if (!latestPreview) throw new Error('latest_etag_preview_not_ready');
      await preview.waitFor({ timeout: 65000 });
      await page.waitForFunction(expectedUrl => {
        const img = document.querySelector('.preview-stage img');
        return img?.complete && img.naturalWidth > 0 && img.src === expectedUrl;
      }, latestPreview.file_url, { timeout: 10000 });
      rows.push({ name: '保存后服务端权威预览可见', status: 'passed', final_edit_to_preview_ms: Date.now() - finalEditStarted,
        artifact_id: latestPreview.id, draft_etag: savedDraft.etag });
    } catch (error) {
      rows.push({ name: '保存后服务端权威预览可见', status: 'failed', error: String(error.message).slice(0, 200) });
    }
    await page.evaluate(() => {
      document.addEventListener('click', event => {
        if (event.target.closest?.('.el-dropdown-menu__item')) window.__evaluationExportSelection = Date.now();
      }, { capture: true });
    });
    for (const format of ['json', 'docx', 'pdf']) {
      // 下载会打开新标签；恢复 Studio 前台后再量点击，避免后台页面
      // 动画帧节流使 Playwright 的稳定性等待混入后端耗时。
      await page.bringToFront();
      const started = Date.now();
      try {
        await page.evaluate(() => { window.__evaluationExportSelection = 0; });
        const acceptedResponse = page.waitForResponse(response => response.url().endsWith('/exports/') && response.request().method() === 'POST', { timeout: 15000 });
        await page.getByRole('button', { name: '导出 ⌄', exact: true }).click();
        await page.getByRole('menuitem', { name: format === 'json' ? 'JSON Resume 1.3.1' : format === 'docx' ? 'DOCX · ATS 样式' : 'PDF · 正式排版', exact: true }).click();
        const accepted = await acceptedResponse;
        const data = await accepted.json();
        if (accepted.status() !== 202 || !data.artifact_id) throw new Error('export_not_accepted_' + accepted.status());
        const deadline = Date.now() + 40000;
        let artifact;
        while (Date.now() < deadline) {
          artifact = artifacts.get(data.artifact_id);
          if (artifact?.status === 'ready' || artifact?.status === 'failed') break;
          await page.waitForTimeout(200);
        }
        if (artifact?.status !== 'ready') throw new Error(artifact?.error_code || 'artifact_not_ready');
        const readyObserved = Date.now();
        const selectionAt = await page.evaluate(() => window.__evaluationExportSelection);
        const exportRequest = networkTimings.find(item => item.started >= started && item.path.endsWith('/exports/') && item.method === 'POST');
        const file = await page.request.get(artifact.file_url);
        const bytes = await file.body();
        const valid = file.ok() && (format === 'json' ? JSON.parse(bytes.toString()).basics.summary === finalText :
          format === 'pdf' ? bytes.subarray(0, 5).toString() === '%PDF-' : bytes.subarray(0, 2).toString() === 'PK');
        rows.push({ name: '浏览器导出并下载 ' + format.toUpperCase(), status: valid ? 'passed' : 'failed',
          format, artifact_id: data.artifact_id, operation_id: data.operation_id, bytes: bytes.length,
          click_to_download_ms: Date.now() - started,
          stage_timings_ms: {
            menu_selection: selectionAt ? selectionAt - started : null,
            selection_to_export_request: selectionAt && exportRequest ? exportRequest.started - selectionAt : null,
            export_request_to_accepted: exportRequest ? exportRequest.ended - exportRequest.started : null,
            accepted_to_ready_observed: exportRequest ? readyObserved - exportRequest.ended : null,
            file_download: Date.now() - readyObserved,
          },
          api_requests: networkTimings.filter(item => item.started >= started).map(item => ({
            kind: item.path.split('/').filter(Boolean).slice(-1)[0], method: item.method,
            status: item.status, start_offset_ms: item.started - started, duration_ms: item.ended - item.started,
          })) });
      } catch (error) {
        rows.push({ name: '浏览器导出并下载 ' + format.toUpperCase(), status: 'failed', error: String(error.message).slice(0, 200) });
      }
    }
  }
  if (fixture.session_id) {
    // Legacy media profile only. Platform profile omits interview fixtures.
    await page.evaluate(sessionId => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/dashboard/interview/' + sessionId), fixture.session_id);
    await page.getByText('正在录制面试视频', { exact: false }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(8000);
    await page.getByRole('button', { name: '结束面试', exact: true }).click();
    await page.getByRole('dialog', { name: '确认结束' }).getByRole('button', { name: '确定', exact: true }).click();
    await page.getByText('录像上传成功', { exact: true }).waitFor({ timeout: 30000 });
    rows.push({ name: '真实浏览器录像分片上传受理', status: 'passed', scope: '最终转码及 DB 关联另行校验；报告生成不在本用例范围' });
  }
  } catch (error) {
    rows.push({ name: '浏览器流程执行', status: 'failed', error: String(error.message).slice(0, 500),
      current_path: new URL(page.url()).pathname, login_http_statuses: authStatuses });
  }
  return { rows, user_id: fixture.user_id, session_id: fixture.session_id, resume_id: fixture.resume_id };
}
