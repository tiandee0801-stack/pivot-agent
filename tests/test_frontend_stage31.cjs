const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');
const { chromium, webkit } = require('playwright');

assert(process.env.PIVOT_UI_ORIGIN, 'Start a disposable guest-mode Pivot server and set PIVOT_UI_ORIGIN');
const origin = new URL(process.env.PIVOT_UI_ORIGIN);
assert.equal(origin.protocol, 'http:');
assert.equal(origin.hostname, '127.0.0.1');
const evidence = process.env.PIVOT_UI_EVIDENCE_DIR;
const engine = process.env.PIVOT_BROWSER_ENGINE || 'chromium';
const viewports = [
  [360, 800, true], [390, 844, true], [430, 932, true], [844, 390, true],
  [768, 900, false], [1280, 900, false], [1440, 900, false],
];

async function capture(page, label, width, height) {
  if (!evidence || ![390, 768, 844, 1280, 1440].includes(width)) return;
  await mkdir(evidence, { recursive: true });
  const fullPage = label.startsWith('03-') || label.startsWith('04-');
  if (fullPage) await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(evidence, `${label}-${width}x${height}.png`), fullPage, animations: 'disabled' });
}

async function layout(page, stage) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    page: document.documentElement.scrollWidth,
  }));
  assert(dimensions.page <= dimensions.viewport, `${stage}: horizontal overflow ${JSON.stringify(dimensions)}`);
}

async function touch(locator) {
  const box = await locator.boundingBox();
  assert(box && box.width >= 44 && box.height >= 44, `Undersized touch target ${locator}: ${JSON.stringify(box)}`);
}

async function contrast(locator, label, minimum) {
  const ratio = await locator.evaluate(element => {
    const styles = getComputedStyle(element);
    const channels = color => (color.match(/[\d.]+/g) || []).map(Number);
    const luminance = color => {
      const values = channels(color).slice(0, 3).map(channel => {
        const scaled = channel / 255;
        return scaled <= 0.04045 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
      });
      return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
    };
    let surface = element;
    while (surface) {
      const fill = getComputedStyle(surface).backgroundColor;
      if ((channels(fill)[3] ?? 1) >= 1) {
        const pair = [luminance(styles.color), luminance(fill)].sort((a, b) => b - a);
        return (pair[0] + 0.05) / (pair[1] + 0.05);
      }
      surface = surface.parentElement;
    }
    return 0;
  });
  assert(ratio >= minimum, `${label}: contrast ${ratio.toFixed(2)}, expected ≥${minimum}`);
}

async function navigation(page, label) {
  const current = page.locator('#nav [aria-current="page"]');
  await current.filter({ hasText: label }).waitFor({ state: 'attached' });
  assert.equal(await current.count(), 1);
  assert.equal((await current.textContent()).trim(), label);
}

async function verifyFlow(browser, [width, height, mobile], version) {
  const context = await browser.newContext({ viewport: { width, height }, isMobile: mobile, hasTouch: mobile });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const problems = [];
  page.on('pageerror', error => problems.push(error.message));
  page.on('console', message => { if (message.type() === 'error') problems.push(message.text()); });
  page.on('response', response => { if (response.status() >= 400) problems.push(`${response.status()} ${new URL(response.url()).pathname}`); });
  page.on('requestfailed', request => {
    const failure = request.failure()?.errorText;
    if (failure !== 'net::ERR_ABORTED') problems.push(`${failure} ${new URL(request.url()).pathname}`);
  });
  const read = async () => {
    const response = await page.request.get(new URL('/api/state', origin).href);
    assert.equal(response.status(), 200);
    return response.json();
  };
  const shot = label => capture(page, label, width, height);
  try {
    await page.goto(origin.href);
    const shortcut = page.locator('[data-exp=quick][data-value=short]');
    await shortcut.waitFor();
    await navigation(page, '计划');
    await layout(page, '计划首页');
    assert.equal(await page.locator('meta[name=theme-color]').getAttribute('content'), '#111318');
    await touch(page.locator('button.install'));
    await touch(shortcut);
    for (const tab of await page.locator('#nav button').all()) await touch(tab);
    await contrast(page.getByRole('heading', { level: 1 }), 'plan heading', 4.5);
    assert.equal((await read()).plan.minutes, 60);
    await shot('01-计划首页');

    await shortcut.focus();
    await page.keyboard.press('Enter');
    const quick = page.getByRole('dialog', { name: /30\s*分钟/ });
    await quick.waitFor();
    assert(await quick.evaluate(dialog => dialog.contains(document.activeElement)), 'Dialog must receive focus when opened');
    await touch(quick.getByRole('button', { name: '关闭' }));
    await layout(page, '调整表单');
    await shot('02-调整条件');
    await page.keyboard.press('Escape');
    await quick.waitFor({ state: 'hidden' });
    assert(await shortcut.evaluate(element => document.activeElement === element), 'Closing the dialog must return focus to its opener');
    await shortcut.click();
    await quick.waitFor();
    const form = page.locator('#quick-form');
    await form.locator('[name=equipment]').selectOption('弹力带');
    await form.locator('input[name=condition][value=normal]').check({ force: true });
    await form.locator('button[type=submit]').click();
    await page.waitForURL('**/#task/*');
    const commit = page.locator('#confirm-form button[type=submit]');
    await commit.waitFor();
    await navigation(page, '计划');
    await layout(page, '方案对比');
    await touch(commit);
    await touch(page.locator('.candidate-detail .option-heading').first());
    await contrast(commit, 'confirmation button', 4.5);
    const before = await read();
    assert.equal(before.plan.minutes, 60);
    assert(before.activeTask.options.some(option => option.equipment.includes('弹力带')));
    assert(!before.activeTask.options.some(option => option.equipment.includes('哑铃')));
    await shot('03-方案对比');

    await commit.click();
    await page.getByText('实际：执行未知', { exact: true }).waitFor();
    const saved = await read();
    assert.equal(saved.plan.minutes, 30);
    assert.equal(saved.plan.version, before.plan.version + 1);
    assert.equal(saved.sessions.length, 0);
    await page.getByText('保存回执', { exact: true }).click();
    await page.getByText(/操作编号/).waitFor();
    await layout(page, '保存回执');
    await shot('04-保存回执');
    await page.reload();
    const record = page.getByRole('button', { name: '记录练后反馈', exact: true });
    await record.waitFor();
    assert.equal((await read()).activeTask.receipt.operationId, saved.activeTask.receipt.operationId);

    await record.click();
    const feedback = page.getByRole('dialog', { name: /练得怎么样/ });
    await feedback.waitFor();
    await layout(page, '练后反馈');
    await shot('05-练后反馈');
    assert.equal(await feedback.locator('[name=completion]').inputValue(), '');
    assert.equal(await feedback.locator('[name=minutes]').inputValue(), '');
    await feedback.locator('[name=completion]').selectOption('partial');
    await feedback.locator('[name=minutes]').fill('20');
    await feedback.locator('[name=feeling]').selectOption({ label: '偏累' });
    await feedback.locator('button[type=submit]').click();
    await feedback.waitFor({ state: 'hidden' });
    await page.waitForFunction(async () => (await fetch('/api/state').then(response => response.json())).sessions.length === 1);
    const actual = (await read()).sessions[0];
    assert.equal(actual.minutes, 20);
    assert.equal(actual.completion, 'partial');

    await page.locator('#nav [data-nav=history]').click();
    await navigation(page, '历史');
    await page.waitForURL('**/#history');
    await layout(page, '历史');
    await page.locator('#nav [data-nav=settings]').click();
    await navigation(page, '我的');
    await page.locator('[data-v2=about]').click();
    const about = page.getByRole('dialog', { name: /Pivot/ });
    await about.waitFor();
    assert((await about.innerText()).includes(version), 'The About dialog must display the actual version');
    await about.getByRole('button', { name: '关闭' }).click();
    await about.waitFor({ state: 'hidden' });
    assert.deepEqual(problems, [], `${width}×${height}: unexpected browser errors`);
    console.log(`${engine} ${width}×${height}: plan → comparison → saved receipt → feedback → history; layout and accessibility passed`);
  } finally {
    await context.close();
  }
}

async function main() {
  assert(['chromium', 'webkit'].includes(engine), 'Use chromium or webkit');
  const response = await fetch(new URL('/api/health', origin));
  assert.equal(response.status, 200);
  const health = await response.json();
  assert.equal(health.authRequired, false, 'Use a disposable no-code guest instance');
  assert.match(health.demoVersion, /^\d+\.\d+\.\d+$/);
  const browser = engine === 'webkit'
    ? await webkit.launch()
    : await chromium.launch({ executablePath: process.env.PIVOT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  try {
    for (const viewport of viewports) await verifyFlow(browser, viewport, health.demoVersion);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
