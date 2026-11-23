/* Real file upload path using explicitly synthetic QA readings, isolated visitor. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const origin=process.env.PIVOT_UI_ORIGIN||'http://127.0.0.1:8860';assert(/^http:\/\/127\.0\.0\.1:88(?:60|61|62)$/.test(origin));
const out=path.resolve(__dirname,'../../../output/Pivot-MVP-重做-2026-11-10/全流程验收');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}),context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true}),page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const state=async()=>{const r=await context.request.get(origin+'/api/state');assert.equal(r.status(),200);return r.json();};
 await page.goto(origin+'/#devices');await page.locator('#health-file').waitFor({state:'attached'});
 assert.match(await page.locator('#main').innerText(),/尚无设备记录|未连接/);
 const download=page.waitForEvent('download');await page.locator('[data-v2=health-template]').click();assert((await download).suggestedFilename().endsWith('.csv'));
 await page.locator('[data-v2=health-guide]').click();assert.match(await page.locator('#sheet-body').innerText(),/HealthKit/);await page.locator('[data-action=close-sheet]').click();
 const now=new Date().toISOString();const csv=Buffer.from('type,value,unit,date,source\nresting_hr,58,count/min,'+now+',QA synthetic watch\nhrv_sdnn,44,ms,'+now+',QA synthetic watch\nsleep,7.2,hours,'+now+',QA synthetic watch\n');
 const upload=page.waitForResponse(r=>r.url().endsWith('/api/wearable/import'));await page.locator('#health-file').setInputFiles({name:'qa-only-readings.csv',mimeType:'text/csv',buffer:csv});assert.equal((await upload).status(),200);await page.locator('#device-permission-form').waitFor();
 let s=await state();assert.equal(s.permissions.device,true);assert.equal(s.device.metrics.length,3);assert.equal(s.device.simulated,false);assert(s.device.metrics.every(m=>m.source==='QA synthetic watch'));assert.match(await page.locator('#main').innerText(),/58/);
 await page.screenshot({path:path.join(out,'05-设备导入真实路径.png'),fullPage:true});
 const create=await context.request.post(origin+'/api/tasks',{data:{input:'今天只有30分钟，没有不适，今天练'}});assert.equal(create.status(),200);s=await create.json();assert(s.activeTask.evidence.some(e=>e.device&&e.source==='QA synthetic watch'),'Imported current readings must enter adjustment evidence');
 await page.locator('#device-permission-form [name=allowed]').uncheck();await page.locator('#device-permission-form button').click();await page.waitForTimeout(250);s=await state();assert.equal(s.permissions.device,false);assert(!s.activeTask.evidence.some(e=>e.device),'Turning permission off hides previous device evidence');
 const after=await context.request.post(origin+'/api/tasks',{data:{input:'今天只有30分钟，没有不适，今天练'}});assert.equal(after.status(),200);s=await after.json();assert(!s.activeTask.evidence.some(e=>e.device),'Revoked data must not enter new tasks');
 // Reenable to show retained import then clear through the real confirmation sheet.
 await page.locator('#device-permission-form [name=allowed]').check();await page.locator('#device-permission-form button').click();await page.waitForTimeout(250);s=await state();assert.equal(s.permissions.device,true);await page.locator('[data-v2=disconnect-health]').waitFor();await page.locator('[data-v2=disconnect-health]').click();await page.locator('[data-v2=confirm-disconnect]').click();await page.locator('#sheet').waitFor({state:'hidden'});s=await state();assert.equal(s.device.metrics.length,0);
 assert.deepEqual(errors,[]);const result={passed:true,checks:['CSV template download','Apple/Garmin guide','file picker upload → parsed source/time metrics','current readings included in Agent context','permission off prevents historical and new evidence disclosure','clear data confirmation removes import'],errors,readings:'synthetic QA values, never product user evidence'};fs.writeFileSync(path.join(out,'wearable-results.json'),JSON.stringify(result,null,2));await browser.close();console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
