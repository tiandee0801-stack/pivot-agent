// Run the V1.1.1 PRD baseline checks against a disposable V1.1.3 guest server.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');

const origin = new URL(process.env.PIVOT_UI_ORIGIN || 'http://127.0.0.1:8895');
assert.equal(origin.hostname, '127.0.0.1');
const chrome = process.env.PIVOT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const health = fetch(new URL('/api/health', origin)).then(r => r.json());
const evidenceDir = process.env.PIVOT_UI_EVIDENCE_DIR;

async function start(browser, width = 390, isMobile = true) {
  const context = await browser.newContext({ viewport: { width, height: 844 }, isMobile, hasTouch: isMobile });
  const page = await context.newPage();
  page.setDefaultTimeout(4500);
  await page.goto(origin.href);
  await page.locator('[data-exp=quick][data-value=short]').waitFor();
  const read = async () => (await page.request.get(new URL('/api/state', origin).href)).json();
  assert.equal((await read()).plan.minutes, 60);
  return { context, page, read };
}

async function capture(page, name) {
  if (!evidenceDir) return;
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: path.join(evidenceDir, name), fullPage: true, animations: 'disabled' });
}

async function quick(q, scenario, { equipment, condition = 'normal', minutes, date, time, restriction } = {}) {
  const { page } = q;
  await page.locator(`[data-exp=quick][data-value=${scenario}]`).click();
  const form = page.locator('#quick-form');
  if (equipment) await form.locator('[name=equipment]').selectOption(equipment);
  if (minutes) await form.locator('[name=minutes]').fill(String(minutes));
  if (date) await form.locator('[name=date]').fill(date);
  if (time) await form.locator('[name=time]').fill(time);
  if (restriction) await form.locator('[name=restriction]').fill(restriction);
  await form.locator(`input[name=condition][value=${condition}]`).check({ force: true });
  await form.locator('button[type=submit]').click();
  await page.waitForURL('**/#task/*');
  await form.waitFor({ state: 'hidden' });
  return (await q.read()).activeTask;
}

async function answer(q, text) {
  const form = q.page.locator('#answer-form');
  await form.locator('[name=text]').fill(text);
  await form.getByRole('button', { name: '继续', exact: true }).click();
  await form.waitFor({ state: 'hidden' });
  return (await q.read()).activeTask;
}

async function confirm(q) {
  await q.page.locator('#confirm-form button[type=submit]').click();
  await q.page.getByRole('button', { name: '记录练后反馈', exact: true }).waitFor();
  return q.read();
}

async function verifyInterruptedSave(browser, mode) {
  const q = await start(browser);
  const { page } = q;
  try {
    await quick(q, 'short', { equipment: '弹力带' });
    let posts = 0;
    await page.route('**/api/confirm', async route => {
      posts++;
      if (posts > 1) return route.continue();
      if (mode === 'committed') {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
      }
      await route.abort('failed');
    });
    if (mode === 'unknown') {
      await page.route('**/api/confirm/check', route => route.fulfill({ status: 404, json: { error: '测试：查无确定回执' } }));
    }
    await page.locator('#confirm-form button[type=submit]').click();
    if (mode === 'committed') {
      await page.getByRole('button', { name: '记录练后反馈', exact: true }).waitFor();
      const state = await q.read();
      const id = state.activeTask.receipt.operationId;
      const receipt = await page.request.get(new URL(`/api/operations/${id}`, origin).href);
      assert.equal(receipt.status(), 200);
      assert.equal((await receipt.json()).operation.operationId, id);
      await page.reload();
      await page.getByRole('button', { name: '记录练后反馈', exact: true }).waitFor();
      assert.equal((await q.read()).activeTask.receipt.operationId, id);
      const outsider = await start(browser);
      try {
        assert.equal((await outsider.page.request.get(new URL(`/api/operations/${id}`, origin).href)).status(), 404);
        assert.equal((await outsider.read()).history.length, 0);
      } finally { await outsider.context.close(); }
    } else if (mode === 'not_submitted') {
      const resume = page.getByRole('button', { name: '继续原保存', exact: true });
      await resume.waitFor();
      assert.equal((await q.read()).plan.minutes, 60);
      assert.equal(posts, 1);
      await resume.click();
      await page.getByRole('button', { name: '记录练后反馈', exact: true }).waitFor();
      assert.equal(posts, 2);
      return;
    } else {
      await page.getByText('暂未查到确定结果，请稍后再核对。', { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: '继续原保存', exact: true }).count(), 0);
      assert.equal(await page.locator('#confirm-form button[type=submit]:enabled').count(), 0);
      assert.equal((await q.read()).plan.minutes, 60);
    }
    assert.equal(posts, 1);
  } finally { await q.context.close(); }
}

async function verifyStaleDraft(browser) {
  const q = await start(browser);
  try {
    const draft = await quick(q, 'short', { equipment: '弹力带' });
    const original = (await q.read()).plan;
    const edit = await q.page.request.post(new URL('/api/plan', origin).href, {
      data: { ...original, expectedVersion: original.version, minutes: 55 },
    });
    assert.equal(edit.status(), 200);
    const alternatives = await q.page.request.post(new URL('/api/alternatives', origin).href, {
      data: { items: [{title: '我确认的弹力带备选', minutes: 30, equipment: '弹力带'}] },
    });
    assert.equal(alternatives.status(), 200);
    await q.page.locator('#confirm-form button[type=submit]').click();
    await q.page.getByRole('button', { name: '读取最新计划后重新调整', exact: true }).click();
    await q.page.waitForFunction(old => location.hash !== `#task/${old}`, draft.id);
    await q.page.locator('#confirm-form button[type=submit]').waitFor();
    const next = await q.read();
    assert.equal(next.plan.minutes, 55);
    assert.equal(next.activeTask.original.minutes, 55);
    assert.equal(next.activeTask.requestContext.equipment, '弹力带');
    assert.notEqual(next.activeTask.id, draft.id);
  } finally { await q.context.close(); }
}

async function verifyOfflineAndManual(browser) {
  const q = await start(browser);
  try {
    const { page, context } = q;
    const version = (await q.read()).plan.version;
    const time = new Date().toISOString();
    await page.locator('[data-nav=devices]').first().click();
    await page.locator('#health-file').setInputFiles({ name: 'fixture.csv', mimeType: 'text/csv', buffer:
      Buffer.from(`type,value,unit,date,source\nsleep,7,hours,${time},PRD synthetic fixture\n`) });
    await page.getByText('PRD synthetic fixture', { exact: false }).first().waitFor();
    assert.equal((await q.read()).device.metrics.length, 1);
    const disconnect = await page.request.post(new URL('/api/wearable/disconnect', origin).href, { data: {} });
    assert.equal(disconnect.status(), 200);
    await page.reload();
    await page.locator('[data-nav=today]').first().click();
    const draft = await quick(q, 'short', { equipment: '弹力带' });
    assert.equal(draft.status, 'draft');
    assert(!draft.evidence.some(e => e.device));
    await page.getByRole('button', { name: '保持原安排', exact: true }).click();
    await page.waitForFunction(async () => (await fetch('/api/state').then(x => x.json())).activeTask?.status === 'kept');
    await page.locator('[data-nav=today]').first().click();
    const details = page.locator('details.custom-request');
    await details.locator('summary').click();
    const input = '今天只有 25 分钟，徒手，状态正常。';
    await details.locator('textarea[name=input]').fill(input);
    await context.setOffline(true);
    await details.locator('button[type=submit]').click();
    await details.getByText(/当前离线/).waitFor();
    assert.equal(await details.locator('textarea[name=input]').inputValue(), input);
    await context.setOffline(false);
    await page.reload();
    await page.locator('details.custom-request summary').waitFor();
    assert.equal(await page.locator('textarea[name=input]').inputValue(), input);
    assert.equal((await q.read()).plan.version, version);
  } finally { await q.context.close(); }
}

async function main() {
  const server = await health;
  assert.equal(server.demoVersion, '1.1.3');
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  try {
    for (const width of [360, 390, 430]) {
      const q = await start(browser, width);
      const visible = await q.page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        shortcuts: [...document.querySelectorAll('[data-exp=quick]')].filter(x => x.getBoundingClientRect().bottom <= innerHeight).length,
      }));
      assert(visible.width <= width, `horizontal overflow at ${width}`);
      assert.equal(visible.shortcuts, 3, `first screen at ${width}`);
      await q.context.close();
    }
    const desktop = await start(browser, 1280, false);
    try {
      assert.equal(await desktop.page.locator('[data-exp=quick]').count(), 3);
      assert(await desktop.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await quick(desktop, 'short', { equipment: '弹力带' });
      assert(await desktop.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    } finally { await desktop.context.close(); }
    const weights = await start(browser);
    try {
      const t = await quick(weights, 'short', { equipment: '哑铃' });
      assert.equal(t.status, 'draft');
      assert(t.options.some(o => /哑铃/.test(o.equipment)));
      assert(t.options.length <= 3);
      await weights.page.getByRole('button', { name: '取消这次调整', exact: true }).click();
      await weights.page.waitForFunction(async () => (await fetch('/api/state').then(x => x.json())).activeTask?.status === 'cancelled');
      assert.equal((await weights.read()).plan.minutes, 60);
    } finally { await weights.context.close(); }

    const sample = await start(browser);
    try {
      const t = await quick(sample, 'short', { equipment: '弹力带' });
      assert.equal(t.status, 'draft');
      assert(t.options.some(o => /弹力带/.test(o.equipment)));
      assert(t.options.every(o => !/哑铃/.test(o.equipment)));
      assert(t.excludedCandidates.some(o => /哑铃/.test(o.reason + o.title)));
      assert.equal((await sample.read()).plan.minutes, 60);
      await capture(sample.page, '方案对比-390px.png');
      const saved = await confirm(sample);
      assert.equal(saved.plan.minutes, 30);
      assert.equal(saved.sessions.length, 0);
      await sample.page.getByText('保存回执', { exact: true }).click();
      await capture(sample.page, '单项保存与回执-390px.png');
      await sample.page.getByRole('button', { name: '记录练后反馈', exact: true }).click();
      const form = sample.page.locator('#quick-feedback');
      assert.equal(await form.locator('[name=completion]').inputValue(), '');
      assert.equal(await form.locator('[name=minutes]').inputValue(), '');
      await form.locator('[name=completion]').selectOption('not_done');
      assert.equal(await form.locator('[name=minutes]').inputValue(), '0');
      await form.locator('[name=completion]').selectOption('partial');
      await form.locator('[name=minutes]').fill('20');
      await form.locator('[name=feeling]').selectOption({ label: '偏累' });
      await form.locator('button[type=submit]').click();
      await form.waitFor({ state: 'hidden' });
      const feedback = (await sample.read()).sessions[0];
      assert.equal(feedback.taskId, t.id);
      assert.equal(feedback.completion, 'partial');
      const followup = await quick(sample, 'short', { equipment: '弹力带', condition: 'unknown', minutes: 20 });
      assert.equal(followup.status, 'needs_info');
      assert.match(followup.question, /上次|上一次/);
      assert.match(followup.question, /偏累|疲劳/);
      await capture(sample.page, '练后反馈触发追问-390px.png');
      const options = await answer(sample, '今天仍然有些疲劳，没有明显不适。');
      assert.equal(options.status, 'draft');
      assert(options.options.every(o => o.intensity === 'light'));
    } finally { await sample.context.close(); }
    console.log('D01/D04: conditions, one feedback loop, no defaults. 360/390/430 mobile and 1280 desktop.');

    const ball = await start(browser);
    try {
      const t = await quick(ball, 'ball');
      assert.equal(t.status, 'needs_info');
      assert.match(t.question, /时段|时间|几点/);
      const update = await answer(ball, '可以改到明天19:00，没有明显不适。');
      await ball.page.locator('[name=availabilityConfirmed]').check();
      assert.equal(update.options[0].time, '19:00');
      const before = await ball.read();
      const after = await confirm(ball);
      assert.equal(after.plan.version, before.plan.version + 1);
      assert.equal(after.goalContext.eventDate, before.goalContext.eventDate);
    } finally { await ball.context.close(); }
    const stop = await start(browser);
    try {
      const t = await quick(stop, 'tired', { equipment: '弹力带', condition: 'pain', minutes: 30 });
      assert.equal(t.status, 'stopped');
      assert.equal(t.options.length, 0);
      assert.equal((await stop.read()).plan.minutes, 60);
    } finally { await stop.context.close(); }
    console.log('D02/D03: asks available slot, one write after confirming it, discomfort stops.');

    for (const mode of ['committed', 'not_submitted', 'unknown']) await verifyInterruptedSave(browser, mode);
    await verifyStaleDraft(browser);
    await verifyOfflineAndManual(browser);
    console.log('D05–D09: stale draft, receipt outcomes, reload, isolation, offline input and manual fallback.');
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
