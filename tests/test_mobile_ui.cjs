/* Isolated browser acceptance. PIVOT_UI_ORIGIN must be a disposable test instance. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const origin = process.env.PIVOT_UI_ORIGIN || 'http://127.0.0.1:8858';
const output = process.env.PIVOT_UI_OUTPUT || path.resolve(__dirname,'../artifacts/mobile-ui');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PIVOT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,hasTouch:true,isMobile:true});
 assert(!origin.includes(':8846'), 'Refuse to mutate the existing service');
 await context.request.post(origin+'/api/reset',{data:{}});
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(origin);await page.getByRole('heading',{name:'今天，也动起来。'}).waitFor();
 await page.screenshot({path:path.join(output,'01-today.png'),fullPage:true});
 // All edits use an isolated database, never the user's existing 8846 instance.
 await page.locator('[data-action=edit-plan]').first().click();
 await page.locator('#plan-form [name=title]').fill('测试上肢力量训练');
 await page.locator('#plan-form [name=minutes]').fill('60');
 await page.locator('#plan-form button').click();await page.locator('#sheet').waitFor({state:'hidden'});
 await page.locator('[data-nav=settings]').last().click();
 await page.locator('[data-action=edit-profile]').first().click();
 await page.locator('#profile-form [name=goal]').fill('未来两周维持训练习惯');
 await page.locator('#profile-form [name=sport]').fill('力量训练、篮球');
 await page.locator('#profile-form [name=preferredTime]').fill('18:30');
 await page.locator('#profile-form button').click();await page.locator('#sheet').waitFor({state:'hidden'});
 await page.locator('[data-nav=today]').last().click();
 await page.locator('[data-action=edit-alternatives]').click();
 await page.locator('#alt-rows .altrow').first().locator('[name=title]').fill('测试30分钟力量训练');
 await page.locator('#alt-rows .altrow').first().locator('[name=minutes]').fill('30');
 await page.locator('#alternatives-form button:not([type])').click();await page.locator('#sheet').waitFor({state:'hidden'});
 await page.locator('#agent-input').fill('今天只有30分钟，没有不适，帮我调整原计划');
 await page.locator('#task-form button[type=submit]').click();await page.waitForURL('**/#task/*');
 for(let i=0;i<3&&await page.locator('#answer-form').count();i++){await page.locator('#answer-form textarea').fill('没有不适，今天可训练30分钟，选择已有短时方案');await page.locator('#answer-form button:not([type])').click();await page.waitForTimeout(250);}
 await page.locator('#confirm-form').waitFor();await page.screenshot({path:path.join(output,'02-adjust.png'),fullPage:true});
 await page.locator('#confirm-form button:not([type])').click();await page.getByRole('heading',{name:'计划已保存',exact:true}).waitFor();
 await page.locator('[data-action=record-task]').click();
 await page.locator('#session-form [name=minutes]').fill('28');await page.locator('#session-form [name=feeling]').selectOption('合适');
 await page.locator('#session-form [name=note]').fill('隔离验收记录');
 await page.locator('#session-form button').click();await page.waitForURL('**/#session/*');
 await page.locator('[data-action=edit-record]').click();await page.locator('#session-form [name=minutes]').fill('29');await page.locator('#session-form button').click();await page.locator('#sheet').waitFor({state:'hidden'});
 assert((await page.locator('#main').innerText()).includes('29'));
 await page.locator('[data-nav=history]').last().click();await page.screenshot({path:path.join(output,'03-history.png'),fullPage:true});
 await page.locator('[data-nav=goals]').last().click();await page.locator('.goalchoices label').nth(3).click();await page.locator('#weekly-form button').click();await page.waitForTimeout(250);await page.screenshot({path:path.join(output,'04-goals.png'),fullPage:true});
 await page.locator('[data-nav=training]').last().click();await page.screenshot({path:path.join(output,'05-training-empty.png'),fullPage:true});
 const fixture=process.env.PIVOT_TEST_VIDEO;
 if(fixture){
  await page.locator('#video-file').setInputFiles(fixture);await page.locator('#upload-form [name=consent]').check();await page.locator('#upload-form button').click();
  await page.locator('[data-action=record-video-result]').waitFor({timeout:150000});
  const video=page.locator('#training-video');await video.evaluate(v=>{v.currentTime=1;return v.play();});await page.waitForTimeout(700);await video.evaluate(v=>v.pause());
  assert(await page.locator('#pose-canvas').evaluate(c=>c.width>0));
  await page.screenshot({path:path.join(output,'06-video-result.png'),fullPage:true});
  await page.locator('[data-action=record-video-result]').click();await page.locator('#session-form [name=minutes]').fill('2');await page.locator('#session-form [name=feeling]').selectOption('合适');
  await page.locator('#session-form [name=correctedCount]').fill('5');await page.locator('#session-form [name=correctionReason]').fill('隔离验收人工回看校正');await page.locator('#session-form button').click();await page.waitForURL('**/#session/*');
  assert((await page.locator('#main').innerText()).includes('5 次'));await page.screenshot({path:path.join(output,'07-record-detail.png'),fullPage:true});
 }
 // Verify export is an actual download, not a placeholder.
 await page.locator('[data-nav=settings]').last().click();const downloadPromise=page.waitForEvent('download');await page.locator('[data-action=export]').click();const download=await downloadPromise;assert(download.suggestedFilename().endsWith('.json'));
 await page.screenshot({path:path.join(output,'08-settings.png'),fullPage:true});
 const manifest=await page.request.get(origin+'/manifest.webmanifest');assert.equal(manifest.status(),200);assert.equal((await manifest.json()).display,'standalone');
 await page.waitForFunction(()=>navigator.serviceWorker.controller!==null);await context.setOffline(true);await page.reload();await page.getByText('当前离线，连接恢复后才能读取或保存训练数据。',{exact:true}).waitFor();
 assert(await page.locator('#main').innerText().then(t=>!t.includes('测试上肢力量训练')));
 await context.setOffline(false);await page.locator('[data-action=retry]').click();await page.getByRole('heading',{name:'把节奏交还给自己。'}).waitFor();
 for(const width of [360,390,768]){await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,viewport:'390x844',videoTest:!!fixture,errors,checks:['plan/profile/alternatives edit','Agent clarification → candidate → confirmation','record create/edit','calendar/weekly goals','video upload/inference/overlay/correction','JSON export','PWA manifest + offline no personal cache','360/390/768 widths']},null,2));
 await browser.close();console.log('Mobile UI acceptance passed');
})().catch(e=>{console.error(e);process.exit(1);});
