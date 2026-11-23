// Run against isolated, loopback V1.1.2 guest instances.
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const rulesOrigin = process.env.PIVOT_RULES_ORIGIN;
const modelOrigin = process.env.PIVOT_MODEL_ORIGIN;
const evidenceDir = process.env.PIVOT_UI_EVIDENCE_DIR;
const input = '今天只有30分钟，只有弹力带，状态正常。';
const fallbackLabel = '模型暂未完成处理，已切换到规则';
const modelLabel = '本次由本地模型帮助理解';
const shortcutLabel = '按你填写的条件处理';
const mobile = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };

assert(rulesOrigin, 'Set PIVOT_RULES_ORIGIN to the disposable --rules-only instance');
for (const value of [rulesOrigin, modelOrigin].filter(Boolean)) {
  const origin = new URL(value);
  assert.equal(origin.protocol, 'http:');
  assert.equal(origin.hostname, '127.0.0.1');
}

async function visit(browser, origin, check) {
  const context = await browser.newContext({ ...mobile, serviceWorkers: 'block' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(origin);
    await page.getByRole('heading', { name: '调一下今天的训练' }).waitFor();
    const read = async () => (await page.request.get(new URL('/api/state', origin).href)).json();
    await check(page, read);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function openInput(page, value) {
  await page.locator('.custom-request summary').click();
  await page.locator('#agent-input').fill(value);
  return page.locator('#task-form button[type=submit]');
}

async function showSource(page, expected) {
  const note = page.locator('#main .interpretation-note');
  await note.filter({ hasText: expected }).waitFor();
  assert.equal(await note.textContent(), expected);
}

async function capture(page, file) {
  if (!evidenceDir) return;
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: path.join(evidenceDir, file), animations: 'disabled' });
}

async function checkFallback(browser) {
  await visit(browser, rulesOrigin, async (page, read) => {
    const original = (await read()).plan;
    let release;
    const held = new Promise(resolve => { release = resolve; });
    await page.route('**/api/tasks', async route => {
      await held;
      await route.continue();
    }, { times: 1 });
    const submit = await openInput(page, input);
    try {
      await submit.click();
      await submit.filter({ hasText: '正在整理你的条件…' }).waitFor();
      assert.equal(await submit.isDisabled(), true);
      assert.equal(await page.locator('#agent-input').inputValue(), input);
      assert.equal(await page.locator('#main .interpretation-note').count(), 0);
    } finally {
      release();
    }
    await page.locator('#confirm-form').waitFor();
    await showSource(page, fallbackLabel);
    const draft = await read();
    assert.equal(draft.activeTask.interpretation.source, 'fallback_rules');
    assert.equal(draft.plan.version, original.version);
    assert(draft.activeTask.options.every(option => option.minutes <= 30 && !option.title.includes('哑铃')));
    assert.equal(await page.getByRole('button', { name: '再试一次', exact: true }).count(), 0);

    await page.reload();
    await showSource(page, fallbackLabel);
    await capture(page, '02-规则降级.png');
    for (const width of [360, 390, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), `horizontal overflow at ${width}`);
    }
    await page.setViewportSize(mobile.viewport);
    await page.locator('#confirm-form button[type=submit]').click();
    await page.getByRole('heading', { name: '新安排，准备好了。' }).waitFor();
    await showSource(page, fallbackLabel);
    const saved = await read();
    assert.equal(saved.activeTask.interpretation.requestId, draft.activeTask.interpretation.requestId);
    assert(saved.activeTask.receipt.operationId);
    await capture(page, '04-确认保存.png');
  });
}

async function checkCurrentTurnAndLegacy(browser) {
  await visit(browser, rulesOrigin, async (page, read) => {
    // Change only the view-model response to exercise sequential rendering.
    await page.route('**/api/tasks', async route => {
      const response = await route.fetch();
      const body = await response.json();
      body.activeTask.mode = 'model';
      body.activeTask.interpretation = { ...body.activeTask.interpretation, source: 'model' };
      await route.fulfill({ response, json: body });
    }, { times: 1 });
    await (await openInput(page, '今天只有30分钟，状态正常。')).click();
    await page.locator('#answer-form').waitFor();
    await showSource(page, modelLabel);
    const before = (await read()).activeTask;
    await page.route('**/api/answer', async route => {
      const response = await route.fetch();
      const body = await response.json();
      body.activeTask.mode = 'model';
      await route.fulfill({ response, json: body });
    }, { times: 1 });
    await page.locator('#answer-form [name=text]').fill('只有弹力带。');
    await page.locator('#answer-form').getByRole('button', { name: '继续', exact: true }).click();
    await page.locator('#confirm-form').waitFor();
    await showSource(page, fallbackLabel);
    const after = (await read()).activeTask;
    assert.equal(before.id, after.id);
    assert.notEqual(before.interpretation.requestId, after.interpretation.requestId);

    await page.route('**/api/state', async route => {
      const response = await route.fetch();
      const body = await response.json();
      body.activeTask.mode = 'model';
      delete body.activeTask.interpretation;
      await route.fulfill({ response, json: body });
    }, { times: 1 });
    await page.reload();
    await page.locator('#confirm-form').waitFor();
    assert.equal(await page.locator('#main .interpretation-note').count(), 0);
    assert.equal(await page.getByText('本地模型辅助解析', { exact: true }).count(), 0);
  });
}

async function checkOtherResults(browser) {
  await visit(browser, rulesOrigin, async page => {
    await page.locator('[data-exp=quick][data-value=short]').click();
    const form = page.locator('#quick-form');
    await form.locator('[name=equipment]').selectOption('弹力带');
    await form.locator('input[name=condition][value=normal]').check({ force: true });
    await form.locator('button[type=submit]').click();
    await page.locator('#confirm-form').waitFor();
    await showSource(page, shortcutLabel);
  });
  await visit(browser, rulesOrigin, async page => {
    await (await openInput(page, '今天只有30分钟，状态正常。')).click();
    await page.locator('#answer-form').waitFor();
    await showSource(page, fallbackLabel);
    assert.equal(await page.locator('#answer-form .interpretation-note').count(), 1);
    await capture(page, '03-规则继续追问.png');
  });
  await visit(browser, rulesOrigin, async page => {
    await (await openInput(page, '今天只有30分钟，现在明显不适。')).click();
    await page.getByRole('heading', { name: '先保留原计划' }).waitFor();
    await showSource(page, fallbackLabel);
    assert.equal(await page.locator('#confirm-form').count(), 0);
  });
}

async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.PIVOT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });
  try {
    if (modelOrigin) {
      await visit(browser, modelOrigin, async (page, read) => {
        await (await openInput(page, input)).click();
        await page.locator('#confirm-form').waitFor();
        await showSource(page, modelLabel);
        assert.equal((await read()).activeTask.interpretation.source, 'model');
        await capture(page, '01-真实模型.png');
      });
      console.log('V1.1.2 real local model rendered in Chromium.');
    }
    await checkFallback(browser);
    await checkCurrentTurnAndLegacy(browser);
    await checkOtherResults(browser);
    console.log(`V1.1.2 Chromium UI passed: pending, fallback, reload, receipt, current turn, legacy, shortcut, follow-up, safety stop, responsive layout${modelOrigin ? ', real local model' : ''}.`);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
