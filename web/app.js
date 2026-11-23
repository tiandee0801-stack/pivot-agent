'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const iconPaths = {
 today:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 5h4"/>',
 training:'<path d="m8 8 8 8M3 8l5-5m8 18 5-5M4 11l7-7m2 16 7-7"/>',
 history:'<path d="M3 11a9 9 0 1 1 2.2 7M3 5v6h6m3-4v5l3 2"/>',
 goals:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
 settings:'<circle cx="12" cy="8" r="3"/><path d="M5 21v-2c0-7 14-7 14 0v2"/>',
 arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',back:'<path d="M20 12H4m6 6-6-6 6-6"/>',chev:'<path d="m9 5 7 7-7 7"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',check:'<path d="m4 12 5 5L20 6"/>',
 agent:'<path d="m3 17 5-6 4 3 8-9m-5 0h5v5"/>',edit:'<path d="m15 3 6 6M4 15 16 3l5 5L9 20l-6 1z"/>',
 video:'<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 9 5-3v12l-5-3"/>',
 upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4"/>',record:'<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
 trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
 export:'<path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>',watch:'<rect x="5" y="6" width="14" height="12" rx="4"/><path d="m8 6 1-4h6l1 4m-8 12 1 4h6l1-4"/>',
 shield:'<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zM8 12l3 3 5-6"/>',note:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6m-6 4h6m-6 4h4"/>'
};
const icon = name => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name] || iconPaths.note}</svg>`;
const navItems = [['today','计划'],['training','训练'],['devices','设备'],['history','历史'],['settings','我的']];
const statusNames = {needs_info:'待补充信息',draft:'等待你确认',saved:'计划已保存',partial:'部分完成',stopped:'已停止',kept:'保留原计划',cancelled:'已取消',failed:'保存未完成'};
const completionNames = {completed:'已完成',partial:'部分完成',not_done:'未训练'};
const interpretationLabels = new Map([
 ['model','本次由本地模型帮助理解'],
 ['fallback_rules','模型暂未完成处理，已切换到规则'],
 ['structured_rules','按你填写的条件处理'],
]);
function interpretationNote(task) {
 const source=task.interpretation?.source;
 const label=interpretationLabels.get(source);
 if(!label)return '';
 const tone=source==='fallback_rules'?'notice warn':'micro';
 return `<p class="interpretation-note ${tone}">${label}</p>`;
}
let state = null, health = null, auth = null, loadingError = '', busy = false, toastTimer, deferredInstall;
let taskInput = '', answerInput = '', selectedOption = '', selectedTask = '', calendarMonth = new Date().toISOString().slice(0,7), selectedDate = '';
let videoState = {file:null,blobUrl:'',job:null,result:null,side:'left',progress:0,uploading:false,error:'',consent:false,overlay:true};
const viewedDrafts = new Set();
let pollTimer = null, overlayFrame = null, pendingConfirmation = null, recordFormKey = null;
let answerTaskId = '';
try {
  pendingConfirmation = JSON.parse(sessionStorage.getItem('pivot-pending-save') || 'null');
  if(pendingConfirmation)pendingConfirmation.stage='unknown';
  const input=JSON.parse(sessionStorage.getItem('pivot-draft-input')||'{}');
  taskInput=input.taskInput||'';answerInput=input.answerInput||'';answerTaskId=input.answerTaskId||'';
} catch {}
const uid = () => crypto.randomUUID ? crypto.randomUUID() : [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('');
const todayISO = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const dateLabel = value => {if(!value)return '';const d=new Date(String(value).slice(0,10)+'T12:00:00');return Number.isNaN(+d)?String(value):new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'long'}).format(d);};
const stamp = s => String(s ?? '').replace('T',' ').replace(/([0-9]{2}:[0-9]{2}):[0-9]{2}.*$/,'$1');
const validMedia = s => typeof s==='string' && /^\/media\/[A-Za-z0-9_-]+\.mp4$/.test(s) ? s : '';
function route(){const [page,id='']=location.hash.slice(1).split('/');return {page:['today','training','devices','history','goals','settings','task','session'].includes(page)?page:'today',id};}
function go(page){if(location.hash==='#'+page)render();else location.hash=page;}
function notify(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('show');toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4000);}
function head(title,sub='',right=''){return `<div class="pagehead"><div>${sub?`<div class="eyebrow">${esc(sub)}</div>`:''}<h1>${esc(title)}</h1></div>${right}</div>`;}
function button(action,label,style='primary',attrs=''){return `<button type="button" class="btn ${style}" data-action="${action}" ${attrs}>${label}</button>`;}
function section(title,link=''){return `<div class="sectionhead"><h2>${esc(title)}</h2>${link}</div>`;}
const errorBox = () => '<div class="error" role="alert"></div>';
const schedule = p => p?`${esc(p.date)} · ${esc(p.time)} · ${esc(p.minutes)} 分钟`:'';
let sheetOpener=null,sheetOpenedAt='',clickedSheetOpener=null;
function showSheet(content){
 const sheet=$('#sheet'),body=$('#sheet-body');
 body.innerHTML=content;
 const title=body.querySelector('h2');
 if(title){title.id='sheet-title';title.tabIndex=-1;sheet.setAttribute('aria-labelledby',title.id);}
 else sheet.removeAttribute('aria-labelledby');
 if(!sheet.open){
  sheetOpener=clickedSheetOpener||document.activeElement;
  sheetOpenedAt=location.hash;
  sheet.showModal();
 }
 (title||sheet.querySelector('[data-action="close-sheet"]')).focus({preventScroll:true});
}
function closeSheet(){$('#sheet').close();}
function setPending(value){pendingConfirmation=value;try{if(value)sessionStorage.setItem('pivot-pending-save',JSON.stringify(value));else sessionStorage.removeItem('pivot-pending-save');}catch{}}
function persistDraftInput(){try{
  if(taskInput||answerInput)sessionStorage.setItem('pivot-draft-input',JSON.stringify({taskInput,answerInput,answerTaskId}));
  else sessionStorage.removeItem('pivot-draft-input');
}catch{}}
function hasPendingConfirmation(taskId){return !!pendingConfirmation && pendingConfirmation.taskId===taskId;}
function confirmationBlocked(){return !!pendingConfirmation || !navigator.onLine;}
function pendingOperationNotice(){
  const p=pendingConfirmation;if(!p)return '';
  const checking=p.stage==='checking',resumable=p.stage==='not_submitted';
  const message=p.stage==='committed'?'已找到原保存回执，正在读取最新计划。':checking?'正在查询原操作回执。':p.message||'保存结果暂未确认，联网后核对原操作。';
  return `<section class="notice warn pending-operation" role="status"><strong>${p.stage==='committed'?'已找到回执':'保存结果待核对'}</strong><p>${esc(message)}</p>${p.operation?.operationId?`<small>操作编号 ${esc(p.operation.operationId)}</small>`:''}<div class="actions">${checking?'':button('check-operation','核对保存结果','soft')}${resumable?button('resume-operation','继续原保存','primary'):''}</div></section>`;
}
function syncConfirmationControls(){
  const panel=$('#operation-status');if(panel)panel.innerHTML=pendingOperationNotice();
  const form=$('#confirm-form');
  if(form)for(const submit of form.querySelectorAll('button[type=submit],button:not([type])')){
    if(confirmationBlocked()&&!submit.disabled){submit.disabled=true;submit.dataset.receiptBlocked='1';}
    else if(!confirmationBlocked()&&submit.dataset.receiptBlocked){submit.disabled=false;delete submit.dataset.receiptBlocked;}
  }
}
function displayError(error,form){const box=form?.querySelector('.error');if(box){box.textContent=error.message;if(error.status===409)box.insertAdjacentHTML('beforeend','<div><button type="button" class="linkbtn" data-action="latest-plan">读取最新计划后重新调整</button></div>');}else notify(error.message);}
const apiErrorFormatHeader='X-Pivot-Error-Format';
function apiResponseError(data,status,fallback){
 const details=data?.error;
 const message=typeof details==='string'?details:details?.message;
 const error=new Error(typeof message==='string'&&message?message:fallback);
 error.status=status;
 error.code=details?.code??data?.code;
 return error;
}
async function api(path,body,method){
 if(!navigator.onLine){const e=new Error('当前离线，尚未保存。请联网后重试。');e.transport=true;throw e;}
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='confirm'||path==='confirm/check'?12000:90000);
 try{
  const options={cache:'no-store',credentials:'same-origin',signal:controller.signal,headers:{[apiErrorFormatHeader]:'structured'}};
  if(body!==undefined){options.method=method||'POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
  else if(method)options.method=method;
  const response=await fetch('/api/'+path,options);let data;try{data=await response.json();}catch{const e=new Error('服务返回的内容无法读取，请重新连接后核对。');e.transport=true;throw e;}
  if(!response.ok){const e=apiResponseError(data,response.status,'请求未完成，请重试。');if(response.status===401&&path!=='auth/pair'){state=null;auth={authenticated:false,pairingRequired:true};render();}throw e;}
  return data;
 }catch(e){if(e.name==='AbortError'){const error=new Error('请求超时，操作结果暂未确认。请先核对记录，避免重复提交。');error.transport=true;throw error;}if(e instanceof TypeError){const error=new Error('连接中断，操作结果暂未确认。请恢复连接后核对。');error.transport=true;throw error;}throw e;}finally{clearTimeout(timer);}
}
async function mutation(path,payload,control,success,method){
 if(busy)return false;
 busy=true;
 const form=control?.closest('form'),old=control?.innerHTML;
 const interpreting=path==='tasks'||path==='answer';
 const progress=interpreting ? $('#interpretation-progress') : null;
 if(progress)progress.textContent='正在整理你的条件';
 if(control){control.disabled=true;control.textContent=interpreting?'正在整理你的条件…':'正在保存…';}
 if(form?.querySelector('.error'))form.querySelector('.error').textContent='';
 try{
  state=await api(path,payload,method);
  if(success)success();
  render();
  if(progress)progress.textContent=interpretationLabels.get(state.activeTask?.interpretation?.source)||'';
  return true;
 }catch(e){
  if(progress)progress.textContent='';
  displayError(e,form);
  return false;
 }finally{
  busy=false;
  if(control?.isConnected){control.disabled=false;control.innerHTML=old;}
 }
}
async function refresh(){try{state=await api('state');loadingError='';render();return true;}catch(e){loadingError=e.message;render();return false;}}
async function boot(){
 try{[health,auth]=await Promise.all([api('health'),api('auth')]);if(auth.authenticated){state=await api('state');loadingError='';}else state=null;}catch(e){loadingError=e.message;}
 render();
 if(state&&pendingConfirmation&&navigator.onLine)void checkOperation();
 if(state){let id;try{id=localStorage.getItem('pivot-last-video-id');}catch{}if(id)resumeVideo(id,false);}
}
function render(){
 if(overlayFrame){cancelAnimationFrame(overlayFrame);overlayFrame=null;}
 const r=route();$('#offline').hidden=navigator.onLine;
 const activeNav={task:'today',session:'history',goals:'settings'}[r.page]||r.page;
 $('#nav').innerHTML=navItems.map(([name,title])=>`<button type="button" class="navbtn ${activeNav===name?'on':''}" data-nav="${name}" ${activeNav===name?'aria-current="page"':''}>${icon(name==='devices'?'watch':name)}<span>${title}</span></button>`).join('');
 if(auth && !auth.authenticated){$('#main').innerHTML=pairView();return;}
 if(!state){$('#main').innerHTML=`${head('连接你的 Pivot')}<div class="card"><p class="subtle" role="${loadingError?'alert':'status'}">${esc(loadingError||'正在读取个人计划…')}</p>${taskInput||answerInput?'<p class="micro">输入已保留在当前浏览器。联网后可继续。</p>':''}${loadingError?`<div class="actions">${button('retry','重新连接')}</div>`:''}</div>`;return;}
 const views={today:todayView,training:trainingView,devices:devicesView,history:historyView,goals:goalsView,settings:settingsView,task:taskView,session:sessionView};
 $('#main').innerHTML=`<div id="operation-status"></div>${views[r.page]()}`;
 syncConfirmationControls();
 if(r.page==='training')attachVideo();
 if(r.page==='task'){const task=currentTask(),key=task?.id+':'+task?.draftVersion;if(task?.status==='draft'&&!viewedDrafts.has(key)){viewedDrafts.add(key);requestAnimationFrame(()=>api('events',{eventId:uid(),event:'draft_view',taskId:task.id,draftVersion:task.draftVersion}).catch(()=>{}));}}
}
function pairView(){return `${head('连接你的 Pivot','个人运动空间')}<form id="pair-form" class="card"><h2>输入访问码</h2><p class="subtle textbody">访问码由这台 Pivot 服务的拥有者提供，连接后才能查看个人计划和视频。</p><label class="field">访问码<input name="code" type="password" autocomplete="off" required maxlength="200"></label>${errorBox()}<button class="btn primary wide">连接</button></form>`;}
function planCard(){const p=state.plan;return `<section class="card limecard"><div class="planhead"><span class="tag">${icon('today')}${state.planIsExample?'示例计划 · 请先编辑':'已保存的计划'}</span><button class="iconbtn" data-action="edit-plan" aria-label="编辑训练计划">${icon('edit')}</button></div><h2 class="plan-title">${esc(p.title)}</h2><div class="plan-duration"><b>${esc(p.minutes)}</b><span>分钟</span></div><div class="plan-foot"><span>${icon('clock')}${esc(p.date===todayISO()?'今天':p.date)} ${esc(p.time)}</span><span>${esc(p.source||'已有计划')}</span></div></section>`;}
function todayView(){const ongoing=state.activeTask&&['needs_info','draft'].includes(state.activeTask.status);const records=state.sessions||[];return `${head('今天，也动起来。',dateLabel(todayISO()))}${planCard()}
<section class="card"><div class="agenthead">${icon('agent')}PIVOT PERSONAL AGENT</div>${ongoing?`<h2 class="agent-title">把这次调整接着做完</h2><p class="textbody">${esc(state.activeTask.input)}</p><p class="subtle textbody" style="margin-top:10px">${esc(statusNames[state.activeTask.status])}</p><div class="actions"><button class="btn primary" data-nav="task/${esc(state.activeTask.id)}">继续调整${icon('arrow')}</button></div>`:`<form id="task-form"><h2 class="agent-title">计划有变？一起调整。</h2><label class="hidden" for="agent-input">告诉 Pivot 你的变化</label><textarea id="agent-input" name="input" maxlength="500" required placeholder="今天只剩 30 分钟，怎么安排？">${esc(taskInput)}</textarea><div class="chips"><button type="button" class="chip" data-prompt="今天只有30分钟，帮我调整原计划">时间变少</button><button type="button" class="chip" data-prompt="昨天临时打了篮球，今天想调整原计划">临时打球</button><button type="button" class="chip" data-prompt="今天有点疲劳，帮我看看原计划怎么调整">有点疲劳</button></div>${errorBox()}<button class="btn primary wide" type="submit">开始调整${icon('arrow')}</button></form>`}
<p class="micro" style="margin-top:13px">${state.model?.available?'本地模型辅助理解请求':'当前使用规则辅助模式'} · 每次改动都由你确认</p></section>
${pendingConfirmation?`<div class="notice warn">有一次保存结果尚未确认。<button class="linkbtn" data-action="check-operation">核对保存结果</button></div>`:''}
${section('实际训练',`<button class="linkbtn" data-action="add-record">手动记录 +</button>`)}${records.length?`<div class="card list">${records.slice(0,2).map(sessionRow).join('')}</div>`:`<div class="empty">${icon('training')}<h3>第一条记录，从这次开始</h3><p>上传一组弯举视频，或手动记录实际训练。计划保存与训练完成会分别记录。</p><div class="actions"><button class="btn primary" data-nav="training">记录训练${icon('arrow')}</button></div></div>`}
${section('已有替代方案',`<button class="linkbtn" data-action="edit-alternatives">管理</button>`)}<div class="card list">${(state.alternatives||[]).map(a=>`<div class="row"><span class="rowicon">${icon('training')}</span><div class="rowmain"><strong>${esc(a.title)}</strong><small>${esc(a.source||'已保存的方案')}</small></div><span class="rowend">${esc(a.minutes)} 分钟</span></div>`).join('')||'<p class="subtle textbody" style="padding:20px 0">还没有替代方案。先保存你认可的短时方案，调整时才有据可依。</p>'}</div>`;}
function taskView({reference='',answerAction=''}={}){const t=[state.activeTask,...(state.history||[])].find(x=>x?.id===route().id);if(!t)return `${head('未找到这次调整')}<button class="btn primary" data-nav="history">返回记录</button>`;
 let body='';
 if(t.status==='needs_info')body=`<form id="answer-form" class="card"><h2>还需要了解一点</h2>${interpretationNote(t)}<p class="textbody" style="margin:16px 0">${esc(t.question)}</p><textarea name="text" required maxlength="500" placeholder="写下这次的真实情况…">${esc(answerTaskId===t.id?answerInput:'')}</textarea>${errorBox()}<div class="actions"><button class="btn primary">继续</button>${answerAction}${button('keep','保留原计划','soft')}${button('cancel','取消这次调整','link')}</div></form>`;
 else if(t.status==='draft'){
 if(selectedTask!==`${t.id}:${t.draftVersion}`){selectedTask=`${t.id}:${t.draftVersion}`;selectedOption=t.options?.[0]?.id||'';}
 body=`<form id="confirm-form" class="card"><h2>选一个适合你的安排</h2><div class="plan-mini"><small>调整前</small><h3>${esc(t.original?.title)}</h3><p class="micro">${schedule(t.original)}</p>${t.original?.content?`<p class="candidate-content">${esc(t.original.content)}</p>`:''}</div><fieldset><legend>候选安排</legend>${(t.options||[]).map(o=>`<label class="option"><input type="radio" name="optionId" value="${esc(o.id)}" required ${o.id===selectedOption?'checked':''}><span><strong>${esc(o.title)}</strong><p>${schedule(o)}</p>${o.purpose?`<p class="candidate-purpose">${esc(o.purpose)}</p>`:''}${o.content?`<p class="candidate-content">${esc(o.content)}</p>`:''}<p>${esc(o.reason)}</p></span></label>`).join('')}</fieldset><div id="availability-confirm" ${(t.options||[]).find(o=>o.id===selectedOption)?.requiresAvailabilityConfirmation?'':'hidden'}><label class="check"><input type="checkbox" name="availabilityConfirmed" ${(t.options||[]).find(o=>o.id===selectedOption)?.requiresAvailabilityConfirmation?'required':'disabled'}><span>我确认所选新时段有空，可以安排训练</span></label></div>${!state.permissions.save?'<div class="notice warn">保存权限已关闭，可在「我的」中开启。</div>':''}${errorBox()}<div class="actions"><button class="btn primary" ${!t.options?.length?'disabled':''}>确认并保存</button>${button('keep','保留原计划','soft')}${button('revise','重新描述变化','link')}</div><p class="micro" style="margin-top:12px">只有收到成功回执后才会显示已保存。不会自动修改其他安排。</p></form>`;
 }else{const saved=t.receipt?.planSaved;body=`<section class="card"><div class="successmark">${icon(saved?'check':'note')}</div><h2 class="center">${esc(statusNames[t.status]||t.status)}</h2><p class="subtle textbody" style="margin-top:15px">${esc(t.receipt?.message||t.reason||'本次任务已结束。')}</p>${saved?`<div class="actions">${button('record-task','记录实际训练')}</div><p class="micro" style="margin-top:12px">计划已保存，实际执行待记录。</p>`:t.status==='stopped'?`<div class="actions">${button('add-record','只记录感受','soft')}</div>`:''}<div class="actions"><button class="btn soft" data-nav="today">回到今日</button></div></section>`;}
 return `<button class="back" data-nav="today">${icon('back')}返回今日</button>${head('训练调整',statusNames[t.status]||'PIVOT AGENT')}<section class="card"><small>你的请求</small><p class="textbody" style="margin-top:7px">${esc(t.input)}</p>${t.reason&&['needs_info','draft'].includes(t.status)?`<p class="subtle textbody" style="margin-top:12px">${esc(t.reason)}</p>`:''}</section>${reference}${t.status==='needs_info'?'':interpretationNote(t)}${body}<section class="card"><details><summary>查看本次依据与待确认信息</summary><ul class="evidence">${(t.evidence||[]).map(e=>`<li><strong>${esc(e.label)}</strong><p>${esc(e.value)}</p><small>${esc([e.source,stamp(e.at)].filter(Boolean).join(' · '))}</small></li>`).join('')}</ul>${t.unknowns?.length?`<div class="notice warn">${t.unknowns.map(esc).join('；')}</div>`:''}<p class="micro">${esc(stamp(t.createdAt))}</p></details></section>`;
}
function sessionRow(s){return `<button class="row" data-nav="session/${esc(s.id)}"><span class="rowicon">${icon(s.videoJobId?'video':'training')}</span><span class="rowmain"><strong>${s.exerciseName||s.observation?.exerciseName||'训练记录'} · ${esc(completionNames[s.completion]||s.completion)}</strong><small>${esc(s.performedAt||String(s.createdAt).slice(0,10))} · ${esc(s.minutes)} 分钟 · ${esc(s.feeling)}</small></span><span class="rowend">${s.observation?.confirmedCount!=null?esc(s.observation.confirmedCount)+' 次':''}</span>${icon('chev')}</button>`;}
function monthStep(offset){const d=new Date(calendarMonth+'-15T12:00:00');d.setMonth(d.getMonth()+offset);calendarMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;selectedDate='';render();}
function calendar(){const [year,month]=calendarMonth.split('-').map(Number),count=new Date(year,month,0).getDate(),start=(new Date(year,month-1,1).getDay()+6)%7;const recorded=new Set((state.sessions||[]).map(s=>s.performedAt));return `<div class="card"><div class="calendar-head"><button class="iconbtn" data-action="month-prev" aria-label="上个月">${icon('back')}</button><strong>${year} 年 ${month} 月</strong><button class="iconbtn" data-action="month-next" aria-label="下个月">${icon('arrow')}</button></div><div class="calendar-grid">${['一','二','三','四','五','六','日'].map(d=>`<span class="weekday">${d}</span>`).join('')}${'<span></span>'.repeat(start)}${Array.from({length:count},(_,i)=>{const date=`${calendarMonth}-${String(i+1).padStart(2,'0')}`;return `<button class="calday ${date===todayISO()?'today':''} ${date===selectedDate?'active':''} ${recorded.has(date)?'has-record':''}" data-date="${date}" aria-label="${date}${recorded.has(date)?' 有训练记录':''}" aria-pressed="${date===selectedDate}">${i+1}</button>`;}).join('')}</div></div>`;}
function historyView(){const all=state.sessions||[],monthRows=all.filter(s=>s.performedAt?.startsWith(calendarMonth)),shown=selectedDate?all.filter(s=>s.performedAt===selectedDate):monthRows,days=new Set(monthRows.filter(s=>s.completion!=='not_done').map(s=>s.performedAt)).size;return `${head('你的每一次坚持。','TRAINING HISTORY',`<button class="iconbtn" data-action="export" aria-label="导出记录">${icon('export')}</button>`)}<div class="stats"><div class="stat"><b>${days}</b><span>本月训练天数</span></div><div class="stat"><b>${monthRows.reduce((n,s)=>n+Number(s.minutes||0),0)}</b><span>累计分钟</span></div><div class="stat"><b>${monthRows.length}</b><span>训练记录</span></div></div>${calendar()}${section(selectedDate?`${selectedDate} 的记录`:'本月记录',selectedDate?`<button class="linkbtn" data-action="clear-date">查看整月</button>`:`<button class="linkbtn" data-action="add-record">新增 +</button>`)}${shown.length?`<div class="card list">${shown.map(sessionRow).join('')}</div>`:'<div class="empty"><h3>这段时间还没有记录</h3><p>实际完成和未完成都可以记录，帮助下一次安排更合适。</p></div>'}${section('计划调整历史')}<div class="card list">${(state.history||[]).map(t=>`<button class="row" data-nav="task/${esc(t.id)}"><span class="rowmain"><strong>${esc(t.input)}</strong><small>${esc(stamp(t.createdAt))}</small></span><span class="rowend">${esc(statusNames[t.status]||t.status)}</span>${icon('chev')}</button>`).join('')||'<p class="subtle" style="padding:22px 0">还没有调整任务。</p>'}</div>`;}
function weekStats(){const now=new Date(todayISO()+'T12:00:00');const monday=new Date(now);monday.setDate(now.getDate()-(now.getDay()+6)%7);const dates=Array.from({length:7},(_,i)=>{const d=new Date(monday);d.setDate(d.getDate()+i);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;});const done=new Set((state.sessions||[]).filter(s=>s.completion!=='not_done'&&s.minutes>0&&dates.includes(s.performedAt)).map(s=>s.performedAt));return {dates,done};}
function goalsView(){const {dates,done}=weekStats(),goal=state.weeklyGoal||3;return `${head('让运动成为日常。','YOUR GOALS')}<section class="card limecard"><h2>本周运动目标</h2><div class="ring" style="--progress:${Math.min(100,done.size/goal*100)}%"><div class="ringinner"><b>${done.size}<span class="subtle" style="font-size:25px"> / ${goal}</span></b><small>天已完成</small></div></div><div class="weekdots">${dates.map((d,i)=>`<span>${'一二三四五六日'[i]}<b class="${done.has(d)?'done':''}">${done.has(d)?'✓':'·'}</b></span>`).join('')}</div><p class="micro center">按实际训练天数统计，同一天多次训练计为一天。</p></section><form id="weekly-form" class="card"><h2>每周想运动几天？</h2><div class="goalchoices" style="margin:23px 0">${Array.from({length:7},(_,i)=>`<label><input type="radio" name="goal" value="${i+1}" ${goal===i+1?'checked':''}><span>${i+1}</span></label>`).join('')}</div>${errorBox()}<button class="btn primary wide">保存目标</button></form>${section('目标与偏好',`<button class="linkbtn" data-action="edit-profile">编辑</button>`)}<section class="card">${state.profileConfirmed===false?'<div class="notice">当前为示例档案，编辑并保存你的实际目标与偏好后再使用。</div>':''}<dl class="sources">${[['goal','阶段目标'],['sport','常见运动'],['preferredTime','偏好时段'],['constraint','个人约束']].map(([key,label])=>`<dt>${label}</dt><dd>${esc(state.profile[key]||'尚未填写')}</dd>`).join('')}</dl><p class="micro">由你填写和更新，后续调整会参考这些信息。</p></section>`;}
function settingsView(){const per=state.permissions;return `${head('把节奏交还给自己。','PROFILE & PREFERENCES')}<section class="card list"><button class="settingsrow" data-action="edit-profile"><span class="rowicon">${icon('settings')}</span><span class="rowmain"><strong>个人档案</strong><small>目标、运动偏好与约束</small></span>${icon('chev')}</button><button class="settingsrow" data-action="edit-plan"><span class="rowicon">${icon('today')}</span><span class="rowmain"><strong>已有训练计划</strong><small>维护当前安排</small></span>${icon('chev')}</button><button class="settingsrow" data-action="edit-alternatives"><span class="rowicon">${icon('training')}</span><span class="rowmain"><strong>短时替代方案</strong><small>只使用你认可的训练方案</small></span>${icon('chev')}</button></section>
<form id="permission-form" class="card"><h2>使用权限</h2><label class="settingsrow"><span class="rowmain"><strong>保存确认后的计划</strong><small>每次调整仍需单独确认</small></span><input class="toggle" type="checkbox" name="save" ${per.save?'checked':''}></label><label class="settingsrow"><span class="rowmain"><strong>引用设备示例记录</strong><small>当前为模拟设备，尚未连接真实穿戴设备</small></span><input class="toggle" type="checkbox" name="device" ${per.device?'checked':''}></label>${errorBox()}<button class="btn soft wide" style="margin-top:14px">保存权限</button></form>
<section class="card list"><button class="settingsrow" data-action="install"><span class="rowicon">${icon('export')}</span><span class="rowmain"><strong>添加到手机主屏幕</strong><small>像 App 一样打开 Pivot</small></span>${icon('chev')}</button><button class="settingsrow" data-action="export"><span class="rowicon">${icon('note')}</span><span class="rowmain"><strong>导出我的数据</strong><small>计划、反馈、动作观察；不含原视频</small></span>${icon('chev')}</button><button class="settingsrow" data-action="privacy"><span class="rowicon">${icon('shield')}</span><span class="rowmain"><strong>数据与使用说明</strong><small>视频处理、保存及删除</small></span>${icon('chev')}</button>${auth?.pairingRequired?`<button class="settingsrow" data-action="logout"><span class="rowmain"><strong>退出这台设备</strong><small>再次打开需重新输入访问码</small></span>${icon('chev')}</button>`:''}</section><p class="micro center">Pivot · 手机端 MVP<br>当前${state.model?.available?'本地语言模型可用':'使用规则辅助'}${health?.vision?.available?' · 动作分析可用':''}</p>`;}
function trainingView(){const v=videoState,r=v.result,job=v.job,working=v.uploading||['queued','running'].includes(job?.status),media=validMedia(r?.sourceUrl)||v.blobUrl;return `${head('看见自己的进步。','TRAINING STUDIO')}<div class="training-intro"><span class="exercise-pill">${icon('training')}站姿弯举</span></div><div class="capture-actions"><button class="capture-option" data-action="pick-video" ${working?'disabled':''}><span class="capture-circle">${icon('upload')}</span>上传视频</button><button class="capture-option" data-action="record-video" ${working?'disabled':''}><span class="capture-circle red">${icon('record')}</span>拍摄一组</button><button class="capture-option" data-action="capture-guide"><span class="capture-circle">${icon('note')}</span>拍摄指南</button></div><input id="video-file" type="file" accept="video/*" hidden><input id="video-camera" type="file" accept="video/*" capture="environment" hidden>
<div class="video-stage">${media?`<video id="training-video" src="${esc(media)}" controls playsinline preload="metadata"></video><canvas id="pose-canvas" aria-label="与训练视频同步的人体关键点叠加"></canvas>${r?`<div class="rep-overlay"><b id="rep-current">${r.quality==='usable'?'0':'—'}</b><span>${r.quality==='usable'?'播放位置的动作次数':'识别不足 · 不输出次数'}</span></div><div class="video-tools"><button data-action="toggle-overlay" aria-pressed="${v.overlay}">${v.overlay?'隐藏骨架':'显示骨架'}</button></div>`:''}`:`<div class="video-empty">${icon('video')}<h3>用真实视频，记录一组训练</h3><p>拍摄完成后进行动作分析，回放时查看关键点与计数。</p></div>`}${working?`<div class="videostatus" aria-live="polite">${v.uploading?'正在上传视频':'正在分析动作'}<span id="progress-label"> ${Math.round(v.progress)}%</span><div class="progress"><span id="progress-bar" style="width:${v.progress}%"></span></div><small>${v.uploading?'请保持页面打开':'视频上传完成，正在提取动作信息'}</small></div>`:''}</div>
${v.file?`<p class="uploadname">${esc(v.file.name)} · ${(v.file.size/1024/1024).toFixed(1)} MB</p>`:''}
${r&&!media?'<div class="notice warn">这段视频已删除或超过保存期限，动作观察仍保留。可重新上传视频查看骨架回放。</div>':''}${v.error?`<div class="notice warn" role="alert">${esc(v.error)}${job?.id||job?.jobId?`<button class="linkbtn" data-action="retry-job">重新检查分析状态</button>`:''}</div>`:''}
${!r&&!working?`<form id="upload-form" class="card"><h2>选择观察侧</h2><div class="segmented"><label><input type="radio" name="side" value="left" ${v.side==='left'?'checked':''}><span>左臂</span></label><label><input type="radio" name="side" value="right" ${v.side==='right'?'checked':''}><span>右臂</span></label></div><label class="check"><input type="checkbox" name="consent" required ${v.consent?'checked':''}><span>将此视频提交到我的 Pivot 服务进行动作分析<small>视频不会发送给公共模型。请确保画面中只有你本人或已取得拍摄授权。</small></span></label>${errorBox()}<button class="btn primary wide" ${v.file?'':'disabled'}>${icon('agent')}分析这组动作</button><p class="filehint">支持 0.3–45 秒、60 MB 以内的视频。当前支持站姿弯举，拍摄后分析。</p></form>`:''}
${r?`<section class="card"><div class="buttonrow"><h2>这组动作的观察</h2><span class="badge ${r.quality==='usable'?'':'warn'}">${r.quality==='usable'?'可记录':'需人工核对'}</span></div><div class="result-grid"><div><b>${r.quality==='usable'&&r.count!=null?esc(r.count):'—'}</b><span>模型观察次数</span></div><div><b>${Math.round((r.validRatio||0)*100)}<small>%</small></b><span>有效关键点帧占比</span></div></div><p class="textbody">${esc(r.summary||'请结合原视频检查观察结果。')}</p><p class="micro" style="margin-top:10px">只记录动作表现，不据此自动增加训练强度或作康复判断。</p><div class="actions">${button('record-video-result','核对并记录训练')}${button('new-video','再记录一组','soft')}</div><details><summary>识别范围与数据来源</summary><p class="micro">${esc(r.side==='right'?'右臂':'左臂')} · ${Number(r.duration||0).toFixed(1)} 秒 · ${esc(r.mode||'姿态模型与动作计数规则')}</p><p class="micro" style="margin-top:7px">${esc(Array.isArray(r.limitations)?r.limitations.join('；'):r.limitations||'衣物遮挡、离开画面及拍摄角度可能影响结果。')}</p></details></section>`:''}
${section('最近上传',`<button class="linkbtn" data-action="refresh-videos">刷新</button>`)}<div class="card list">${(state.videoJobs||[]).slice(0,6).map(j=>`<div class="row"><button class="settingsrow" data-open-job="${esc(j.jobId||j.id)}" style="padding:0"><span class="rowicon">${icon('video')}</span><span class="rowmain"><strong>${j.status==='done'?'弯举动作观察':j.status==='error'?'分析未完成':'正在分析'}</strong><small>${esc(stamp(j.createdAt))}</small></span>${icon('chev')}</button><button class="iconbtn" data-delete-job="${esc(j.jobId||j.id)}" aria-label="删除这段训练视频">${icon('trash')}</button></div>`).join('')||'<p class="subtle textbody" style="padding:22px 0">尚未上传视频。</p>'}</div>`;}
function sessionView(){const s=(state.sessions||[]).find(x=>x.id===route().id);if(!s)return `${head('记录已不存在')}<button class="btn primary" data-nav="history">查看全部记录</button>`;const o=s.observation,src=validMedia(o?.sourceUrl);return `<button class="back" data-nav="history">${icon('back')}返回记录</button>${head((s.exerciseName||s.observation?.exerciseName||'训练')+'记录',dateLabel(s.performedAt))}<section class="card"><span class="badge">${esc(completionNames[s.completion])}</span><div class="stats"><div class="stat"><b>${esc(s.minutes)}</b><span>实际分钟</span></div><div class="stat"><b>${o?.confirmedCount!=null?esc(o.confirmedCount):'—'}</b><span>${o?'确认次数':'未附动作观察'}</span></div><div class="stat"><b style="font-size:24px">${esc(s.feeling)}</b><span>训练感受</span></div></div><p class="textbody">${s.discomfort?'本次记录有身体不适':'本次未报告身体不适'}</p>${s.note?`<div class="notice">${esc(s.note)}</div>`:''}${o?`<dl class="sources"><dt>原始模型观察</dt><dd>${o.originalCount!=null?esc(o.originalCount)+' 次':'识别不足，未输出次数'} · ${o.quality==='usable'?'可记录':'需人工核对'}</dd><dt>人工核对</dt><dd>${o.confirmedCount!=null?esc(o.confirmedCount)+' 次':'未提供校正次数'}${o.correctionReason?' · '+esc(o.correctionReason):''}</dd></dl>`:''}${src?`<video class="historyvideo" src="${esc(src)}" controls playsinline preload="metadata"></video><button class="linkbtn" data-open-job="${esc(s.videoJobId)}">查看骨架回放${icon('arrow')}</button>`:o?'<p class="micro" style="margin-top:14px">未保留可播放的视频，结构化观察仍在此记录中。</p>':''}<div class="actions">${button('edit-record','编辑记录','soft')}${button('delete-record','删除记录','danger')}</div><p class="micro" style="margin-top:15px">最后更新 ${esc(stamp(s.updatedAt||s.createdAt))} · 版本 ${esc(s.revision||1)}</p></section>`;}
function editPlan(){const p=state.plan;showSheet(`<h2>编辑已有计划</h2><p class="micro">保存后，尚未确认的旧调整方案需要重新生成。</p><form id="plan-form" data-version="${esc(p.version)}"><label class="field">训练名称<input name="title" value="${esc(p.title)}" required maxlength="100"></label><div class="formgrid"><label class="field">日期<input type="date" name="date" value="${esc(p.date)}" required></label><label class="field">开始时间<input type="time" name="time" value="${esc(p.time)}" required></label></div><label class="field">计划时长（分钟）<input type="number" name="minutes" value="${esc(p.minutes)}" min="1" max="240" step="1" required></label><label class="field">训练目的<input name="purpose" value="${esc(p.purpose||'')}" maxlength="120" placeholder="如维持力量、为篮球保持状态"></label><label class="field">具体训练内容<textarea name="content" maxlength="1500" placeholder="填写已有动作、组次和重量，调整时会展示内容差异">${esc(p.content||'')}</textarea></label><label class="field">场地与器械<input name="equipment" value="${esc(p.equipment||'')}" maxlength="200" placeholder="如健身房、哑铃"></label>${errorBox()}<button class="btn primary wide">保存计划</button></form>`);}
function editProfile(){showSheet(`<h2>个人目标与偏好</h2><form id="profile-form">${[['goal','当前阶段目标','如保持运动习惯'],['sport','常见运动','如力量训练、篮球'],['preferredTime','偏好训练时段','如工作日傍晚'],['constraint','训练约束','如周六固定球局']].map(([key,label,placeholder])=>`<label class="field">${label}<input name="${key}" maxlength="120" value="${esc(state.profile[key])}" placeholder="${placeholder}"></label>`).join('')}<div class="formgrid"><label class="field">阶段目标结束日期<input type="date" name="endDate" value="${esc(state.goalContext?.endDate||'')}"></label><label class="field">近期重要运动日期<input type="date" name="eventDate" value="${esc(state.goalContext?.eventDate||'')}"></label></div><label class="field">近期重要运动<input name="eventName" maxlength="100" value="${esc(state.goalContext?.eventName||'')}" placeholder="如周六篮球比赛"></label><p class="micro">信息由你确认后用于后续安排。任何设备记录都不会自动变成长期偏好。</p>${errorBox()}<button class="btn primary wide" style="margin-top:15px">保存档案</button></form>`);}
function altRow(a={}){return `<div class="altrow" data-id="${esc(a.id||'')}"><div class="alt-top"><input name="title" value="${esc(a.title||'')}" required maxlength="80" placeholder="已认可的训练方案" aria-label="方案名称"><input name="minutes" type="number" value="${esc(a.minutes||30)}" required min="1" max="240" step="1" aria-label="方案分钟数"><button class="iconbtn" type="button" data-action="remove-alt" aria-label="移除方案">×</button></div><select name="intensity" aria-label="备选负荷"><option value="routine" ${a.intensity!=='light'?'selected':''}>常规训练</option><option value="light" ${a.intensity==='light'?'selected':''}>本人认可的低负荷备选</option></select><input name="purpose" maxlength="120" value="${esc(a.purpose||'')}" placeholder="训练目的" aria-label="备选训练目的"><textarea name="content" maxlength="1500" placeholder="具体动作、组次和重量（已有方案）" aria-label="备选训练内容">${esc(a.content||'')}</textarea><input name="equipment" maxlength="200" value="${esc(a.equipment||'')}" placeholder="场地与器械" aria-label="备选器械"></div>`;}
function editAlternatives(){showSheet(`<h2>已有替代方案</h2><p class="micro">添加你已经认可的方案与时长，Pivot 调整计划时从中选择。最多 8 项。</p><form id="alternatives-form"><div id="alt-rows">${(state.alternatives||[]).map(altRow).join('')}</div><button type="button" class="linkbtn" data-action="add-alt">+ 添加方案</button>${errorBox()}<button class="btn primary wide" style="margin-top:15px">保存替代方案</button></form>`);}
function recordForm({session=null,taskId='',videoJobId='',result=null,quickBasketball=false}={}){recordFormKey=uid();const s=session||{},ob=s.observation;const sourceCount=ob?ob.originalCount:result?.quality==='usable'?result.count:null;const confirmed=ob?.confirmedCount??sourceCount;const active=state.activeTask;const linked=taskId||s.taskId||'';
 const completion=s.completion||(quickBasketball?'completed':'');
 const title=quickBasketball?'记一场篮球':session?'编辑训练记录':'记录实际训练';
 showSheet(`<h2>${title}</h2>${quickBasketball?'':'<p class="micro">计划调整和实际训练分别记录，保存后的反馈可用于下一次调整。</p>'}<form id="session-form" ${quickBasketball?'data-quick-basketball':''} data-id="${esc(s.id||'')}" data-revision="${esc(s.revision||'')}" data-task="${esc(linked)}" data-video="${esc(videoJobId||s.videoJobId||'')}" data-source-count="${sourceCount==null?'':esc(sourceCount)}">
${!quickBasketball&&!session&&!linked&&active?.receipt?.planSaved?`<label class="check"><input type="checkbox" name="linkTask" value="${esc(active.id)}"><span>关联最近一次已保存的调整<small>${esc(active.input)}</small></span></label>`:''}
<div class="formgrid"><label class="field">训练日期<input type="date" name="performedAt" required value="${esc(s.performedAt||todayISO())}" max="${todayISO()}"></label><label class="field">完成情况<select name="completion" required><option value="" ${completion?'':'selected'}>请选择</option>${Object.entries(completionNames).map(([k,v])=>`<option value="${k}" ${completion===k?'selected':''}>${v}</option>`).join('')}</select></label></div><div class="formgrid"><label class="field">实际时长（分钟）<input name="minutes" type="number" min="${completion==='not_done'?0:1}" max="240" step="1" required value="${esc(s.minutes??'')}" placeholder="实际训练时长"></label><label class="field">训练感受<select name="feeling" required><option value="">请选择</option>${['合适','偏累','偏轻松','不合适'].map(v=>`<option ${s.feeling===v?'selected':''}>${v}</option>`).join('')}</select></label></div><label class="check"><input type="checkbox" name="discomfort" ${s.discomfort?'checked':''}><span>这次训练出现了身体不适</span></label>
${videoJobId||s.videoJobId?`<div class="notice">模型观察 ${sourceCount==null?'识别不足，未给出可靠次数':esc(sourceCount)+' 次'}。请先回看视频再确认；校正将保留原始结果。</div><label class="field">你确认的次数（无法判断可留空）<input type="number" name="correctedCount" min="0" max="1000" step="1" value="${confirmed==null?'':esc(confirmed)}"></label><label class="field">校正原因（更改次数时必填）<input name="correctionReason" maxlength="200" value="${esc(ob?.correctionReason||'')}" placeholder="如遮挡导致漏计，回看后确认"></label>`:''}
<label class="field">补充记录（选填）<textarea name="note" rows="2" maxlength="500" placeholder="实际完成了什么，有什么影响安排的变化？">${esc(s.note||'')}</textarea></label>${errorBox()}<button class="btn primary wide">保存训练记录</button></form>`);}
function clearVideo(){if(videoState.blobUrl)URL.revokeObjectURL(videoState.blobUrl);if(pollTimer)clearTimeout(pollTimer);videoState={file:null,blobUrl:'',job:null,result:null,side:'left',progress:0,uploading:false,error:'',consent:false,overlay:true};try{localStorage.removeItem('pivot-last-video-id');}catch{}}
function setVideoFile(file){
 if(!file)return false;
 if(!file.size){notify('这段视频为空，请重新拍摄或选择其他视频。');return false;}
 if(file.size>60*1024*1024){notify('视频超过 60 MB，请先缩短视频。');return false;}
 if(!file.type.startsWith('video/')&&!/\.(mp4|mov|webm|m4v)$/i.test(file.name)){notify('请选择 MP4、MOV 或 WebM 视频。');return false;}
 clearVideo();videoState.file=file;videoState.blobUrl=URL.createObjectURL(file);render();return true;
}
function updateUploadProgress(progress){videoState.progress=progress;const label=$('#progress-label'),bar=$('#progress-bar');if(label)label.textContent=` ${Math.round(progress)}%`;if(bar)bar.style.width=`${Math.min(100,Math.max(0,progress))}%`;}
async function uploadVideo(form){if(videoState.uploading||!videoState.file)return;if(!navigator.onLine){displayError(new Error('当前离线，无法上传视频。'),form);return;}
 videoState.side=form.elements.side.value;videoState.consent=form.elements.consent.checked;if(!videoState.consent)return;videoState.uploading=true;videoState.error='';videoState.progress=0;const file=videoState.file;render();
 try{
  const response=await new Promise((resolve,reject)=>{
   const xhr=new XMLHttpRequest();
   xhr.open('POST','/api/video?side='+encodeURIComponent(videoState.side)+'&exercise='+encodeURIComponent(selectedExercise));
   xhr.withCredentials=true;
   xhr.timeout=90000;
   xhr.setRequestHeader('Content-Type',file.type||'application/octet-stream');
   xhr.setRequestHeader(apiErrorFormatHeader,'structured');
   xhr.upload.onprogress=e=>{if(e.lengthComputable)updateUploadProgress(e.loaded/e.total*100);};
   xhr.onload=()=>{
    let data;
    try{data=JSON.parse(xhr.responseText);}catch{return reject(new Error('无法读取上传结果，请检查服务。'));}
    if(xhr.status>=200&&xhr.status<300)resolve(data);
    else reject(apiResponseError(data,xhr.status,'视频上传失败。'));
   };
   xhr.onerror=()=>reject(new Error('视频上传连接中断，请联网后重试。'));
   xhr.ontimeout=()=>reject(new Error('视频上传超时。请刷新最近上传，确认是否收到视频。'));
   xhr.send(file);
  });
  videoState.uploading=false;videoState.job=response;videoState.progress=0;try{localStorage.setItem('pivot-last-video-id',response.jobId);}catch{}render();await pollVideo(response.jobId);
 }catch(e){videoState.uploading=false;videoState.error=e.message;render();}
}
async function pollVideo(id){clearTimeout(pollTimer);try{const job=await api('jobs/'+encodeURIComponent(id));videoState.job=job;videoState.error='';videoState.progress=Number(job.progress||0);
 if(job.status==='done'){videoState.result=job.result;state=await api('state');if(route().page==='training')render();else notify('动作分析完成，可在训练页查看。');return;}
 if(job.status==='error'){videoState.error=job.error||'这段视频暂时无法分析，请参考拍摄指南重新录制。';state=await api('state');if(route().page==='training')render();return;}
 if(route().page==='training'){if(!$('#progress-label'))render();else updateUploadProgress(videoState.progress);}pollTimer=setTimeout(()=>pollVideo(id),1400);
 }catch(e){videoState.error=e.message;if(route().page==='training')render();}
}
async function resumeVideo(id,navigate=true){clearTimeout(pollTimer);try{const j=await api('jobs/'+encodeURIComponent(id));if(videoState.blobUrl)URL.revokeObjectURL(videoState.blobUrl);videoState.file=null;videoState.blobUrl='';videoState.job=j;if(j.exercise)selectedExercise=j.exercise;videoState.result=j.status==='done'?j.result:null;videoState.error=j.status==='error'?(j.error||'分析未完成'):'';videoState.progress=j.progress||0;try{localStorage.setItem('pivot-last-video-id',id);}catch{}if(navigate)go(studioRoute());else if(route().page==='training')render();if(['queued','running'].includes(j.status))pollVideo(id);}catch(e){if(e.status===404){try{localStorage.removeItem('pivot-last-video-id');}catch{}}else notify(e.message);}}
function attachVideo(){const video=$('#training-video'),canvas=$('#pose-canvas');if(!video||!canvas)return;const frames=videoState.result?.frames||[],ctx=canvas.getContext('2d');const edges=[[5,6],[5,7],[7,9],[6,8],[8,10],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
 const draw=()=>{if(!video.isConnected)return;const width=video.clientWidth,height=video.clientHeight,dpr=Math.min(devicePixelRatio||1,2);if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
 if(frames.length){let lo=0,hi=frames.length-1;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(frames[mid].t<=video.currentTime)lo=mid;else hi=mid-1;}const f=frames[lo],r=videoState.result;const badge=$('#rep-current');if(badge)badge.textContent=r.quality==='usable'?String(f?.count||0):'—';
 if(videoState.overlay&&f&&Math.abs(f.t-video.currentTime)<.75&&video.videoWidth&&video.videoHeight){const scale=Math.min(width/video.videoWidth,height/video.videoHeight),vw=video.videoWidth*scale,vh=video.videoHeight*scale,ox=(width-vw)/2,oy=(height-vh)/2,points=f.points||[];const point=i=>points[i]&&points[i][2]>=.35?[ox+points[i][0]*vw,oy+points[i][1]*vh]:null;ctx.lineWidth=2.6;ctx.strokeStyle='#bfff30';ctx.shadowColor='#000';ctx.shadowBlur=3;edges.forEach(([a,b])=>{const p=point(a),q=point(b);if(p&&q){ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();}});const arm=r.side==='right'?[6,8,10]:[5,7,9];for(let i=0;i<points.length;i++){const p=point(i);if(p){ctx.beginPath();ctx.arc(...p,arm.includes(i)?4.3:2.8,0,Math.PI*2);ctx.fillStyle=arm.includes(i)?'#fff':'#bfff30';ctx.fill();}}ctx.shadowBlur=0;}}
 overlayFrame=requestAnimationFrame(draw);};draw();}
function currentTask(){return [state?.activeTask,...(state?.history||[])].find(t=>t?.id===route().id);}
function currentSession(){return (state?.sessions||[]).find(s=>s.id===route().id);}
const terminalConfirmationCodes=new Set(['already_confirmed','task_closed','draft_required','draft_expired','stale_draft','slot_conflict','save_denied','availability_confirmation_required','invalid_input','idempotency_conflict']);
function confirmationPayload(p){return {id:p.taskId,optionId:p.optionId,draftVersion:p.draftVersion,remind:false,idempotencyKey:p.key,availabilityConfirmed:!!p.availabilityConfirmed};}
function finishConfirmedOperation(saved){setPending(null);state=saved;render();notify('已核对保存结果。');}
function showConfirmationError(error,form){
  if(form?.isConnected){displayError(error,form);return;}
  const box=$('#confirm-form .error');if(box)displayError(error,box.closest('form'));else notify(error.message);
}
async function sendConfirmation(p,form){
  setPending({...p,stage:'checking'});busy=true;syncConfirmationControls();
  let needsLookup=false,error=null;
  try{const saved=await api('confirm',confirmationPayload(p));finishConfirmedOperation(saved);}
  catch(e){
    error=e;
    if(terminalConfirmationCodes.has(e.code)){setPending(null);render();showConfirmationError(e,form);}
    else{setPending({...p,stage:'unknown',message:'未收到确定的保存结果。正在准备核对原操作。'});render();needsLookup=true;}
  }finally{busy=false;syncConfirmationControls();}
  if(needsLookup&&navigator.onLine)await checkOperation();
  return !error;
}
async function confirmTask(form){
  if(busy)return;
  if(pendingConfirmation){syncConfirmationControls();return;}
  if(!navigator.onLine){showConfirmationError(new Error('当前离线，计划没有保存。恢复连接后可确认。'),form);return;}
  const task=currentTask(),optionId=form.elements.optionId?.value;
  if(!task||!optionId)return;
  const p={key:uid(),taskId:task.id,optionId,draftVersion:task.draftVersion,availabilityConfirmed:!!form.elements.availabilityConfirmed?.checked};
  await sendConfirmation(p,form);
}
async function checkOperation(){
  const p=pendingConfirmation;if(!p||busy)return;
  if(!navigator.onLine){syncConfirmationControls();return;}
  busy=true;setPending({...p,stage:'checking'});syncConfirmationControls();
  try{
    const {operation}=await api('confirm/check',confirmationPayload(p));
    if(!operation||operation.taskId!==p.taskId||operation.idempotencyKey!==p.key)throw new Error('尚未确认原操作。');
    if(operation.status==='succeeded'){
      setPending({...p,stage:'committed',operation});syncConfirmationControls();
      const current=await api('state');finishConfirmedOperation(current);
    }else if(operation.status==='not_submitted'){
      setPending({...p,stage:'not_submitted',message:'原操作尚未提交，确认条件仍有效。可以继续原保存。'});
    }else setPending({...p,stage:'unknown',message:'暂未查到确定结果，请稍后再核对。'});
  }catch(e){
    if(terminalConfirmationCodes.has(e.code)){setPending(null);render();showConfirmationError(e);}
    else if(pendingConfirmation?.stage!=='committed')setPending({...p,stage:'unknown',message:'暂未查到确定结果，请稍后再核对。'});
  }finally{busy=false;syncConfirmationControls();}
}
async function resumeOperation(){
  const p=pendingConfirmation;
  if(!p||p.stage!=='not_submitted'||busy||!navigator.onLine)return;
  await sendConfirmation(p,$('#confirm-form'));
}
async function exportData(){try{const data=await api('export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`Pivot-运动记录-${todayISO()}.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);notify('已生成数据导出文件。');}catch(e){notify(e.message);}}
async function install(){if(deferredInstall){await deferredInstall.prompt();const answer=await deferredInstall.userChoice;if(answer.outcome==='accepted')notify('已请求添加到主屏幕。');deferredInstall=null;return;}const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;if(standalone){notify('你已经在独立 App 窗口中使用 Pivot。');return;}showSheet(`<h2>把 Pivot 放到主屏幕</h2><p class="textbody">手机打开可访问的 HTTPS 地址后，可添加为桌面应用。</p><ol><li><strong>iPhone / iPad</strong><br>在 Safari 打开，点「分享」→「添加到主屏幕」。</li><li><strong>Android</strong><br>在 Chrome 打开，点浏览器菜单 →「安装应用」或「添加到主屏幕」。</li></ol><div class="notice">当前为 ${esc(location.hostname)}。电脑的 127.0.0.1 地址不能直接在手机访问，需使用已配置的手机访问地址。</div><p class="micro">训练记录仍保存在你的 Pivot 服务中，离线时不会假装保存成功。</p>`);}
function captureGuide(){showSheet(`<h2>让动作清楚地被看见</h2><ol><li>本次支持<strong>站姿弯举</strong>。选择要观察的左臂或右臂。</li><li>固定手机，采用侧前方角度，肩、肘、手腕与身体保持在画面中，尽量避免哑铃遮挡关节。</li><li>画面只保留一人，光线充足。完整拍下开始、弯举和回落过程。</li><li>视频长度 0.3–45 秒、文件不超过 60 MB。录完后上传分析，并回放核对次数。</li></ol><p class="micro">这是动作观察工具。识别不足时不会给出可信次数，可以自行核对后校正。是否适合训练仍需结合自身情况判断。</p>`);}
function deleteConfirm(title,description,action,id){showSheet(`<h2>${esc(title)}</h2><p class="textbody">${esc(description)}</p><div class="actions"><button class="btn soft" data-action="close-sheet">取消</button><button class="btn danger" data-action="${action}" data-id="${esc(id)}">确认删除</button></div>`);}
document.addEventListener('input',event=>{
  const input=event.target;
  if(input.name==='input'&&input.form?.id==='task-form'){taskInput=input.value;persistDraftInput();}
  if(input.name==='text'&&input.form?.id==='answer-form'){answerInput=input.value;answerTaskId=currentTask()?.id||'';persistDraftInput();}
});
document.addEventListener('change',event=>{const el=event.target;if(el.id==='video-file'||el.id==='video-camera')return setVideoFile(el.files[0]);if(el.name==='optionId'){selectedOption=el.value;const required=!!currentTask()?.options?.find(o=>o.id===selectedOption)?.requiresAvailabilityConfirmation;const box=$('#availability-confirm');if(box){box.hidden=!required;const check=box.querySelector('input');check.checked=false;check.disabled=!required;check.required=required;}}if(el.closest('#upload-form')){if(el.name==='side')videoState.side=el.value;if(el.name==='consent')videoState.consent=el.checked;}if(el.name==='completion'){const minutes=el.form.elements.minutes;if(el.value==='not_done'){minutes.value='0';minutes.min='0';}else{minutes.min='1';if(minutes.value==='0')minutes.value='';}}});
document.addEventListener('click',async event=>{const el=event.target.closest('button');if(!el)return;if(el.dataset.action==='close-sheet'){closeSheet();return;}if(busy)return;
 if(el.dataset.nav){go(el.dataset.nav);return;}if(el.dataset.prompt){const input=el.closest('form').querySelector('textarea');input.value=el.dataset.prompt;taskInput=input.value;input.focus();return;}if(el.dataset.date){selectedDate=selectedDate===el.dataset.date?'':el.dataset.date;render();return;}
 if(el.dataset.openJob){resumeVideo(el.dataset.openJob);return;}
 if(el.dataset.deleteJob){deleteConfirm('删除这段视频？','将删除视频与分析任务。已保存训练记录中的原始次数和人工校正会保留，视频将不再可播放。','confirm-delete-job',el.dataset.deleteJob);return;}
 const action=el.dataset.action;if(!action)return;const t=currentTask();
 if(action==='retry'){boot();return;}if(action==='install'){install();return;}if(action==='edit-plan'){editPlan();return;}if(action==='edit-profile'){editProfile();return;}if(action==='edit-alternatives'){editAlternatives();return;}
 if(action==='add-alt'){if($('#alt-rows').children.length>=8)return notify('最多保存 8 个替代方案。');$('#alt-rows').insertAdjacentHTML('beforeend',altRow());return;}
 if(action==='remove-alt'){el.closest('.altrow').remove();return;}
 if(action==='keep'||action==='cancel'||action==='revise'){
  if(!t)return;
  if(hasPendingConfirmation(t.id)){notify('先核对这次保存结果，再更改这项调整。');return;}
  await mutation(action==='revise'?'cancel':action,{id:t.id},el,()=>{
    if(answerTaskId===t.id){answerInput='';answerTaskId='';}
    if(action==='revise'){taskInput=t.input;go('today');}
    else notify(action==='keep'?'已保留原计划':'已取消这次调整');
    persistDraftInput();
  });return;
 }
 if(action==='latest-plan'){
  closeSheet();
  if(t&&['draft','needs_info'].includes(t.status)&&!confirmationBlocked()){
    await mutation('tasks',{input:t.input,context:t.requestContext},el,()=>{answerInput='';answerTaskId='';persistDraftInput();go('task/'+state.activeTask.id);notify('已按最新条件重新准备，请再次确认。');});
  }else{await refresh();go('today');}
  return;
 }
 if(action==='check-operation'){void checkOperation();return;}if(action==='resume-operation'){void resumeOperation();return;}if(action==='add-record'){recordForm();return;}if(action==='record-task'){if(t)recordForm({taskId:t.id});return;}
 if(action==='quick-log-basketball'){recordForm({quickBasketball:true});return;}
 if(action==='record-video-result'){recordForm({videoJobId:videoState.job?.jobId||videoState.job?.id,result:videoState.result});return;}
 if(action==='edit-record'){recordForm({session:currentSession()});return;}
 if(action==='delete-record'){const s=currentSession();if(s)deleteConfirm('删除这条训练记录？','将删除这条实际训练反馈，保留原计划调整历史及原视频。此操作无法撤销。','confirm-delete-record',s.id);return;}
 if(action==='confirm-delete-record'){await mutation('sessions/'+encodeURIComponent(el.dataset.id),undefined,el,()=>{closeSheet();go('history');notify('训练记录已删除。');},'DELETE');return;}
 if(action==='confirm-delete-job'){const id=el.dataset.id;await mutation('jobs/'+encodeURIComponent(id),undefined,el,()=>{if((videoState.job?.jobId||videoState.job?.id)===id)clearVideo();closeSheet();notify('视频已删除。');},'DELETE');return;}
 if(action==='month-prev'){monthStep(-1);return;}if(action==='month-next'){monthStep(1);return;}if(action==='clear-date'){selectedDate='';render();return;}
 if(action==='pick-video'){$('#video-file').click();return;}if(action==='record-video'){$('#video-camera').click();return;}if(action==='capture-guide'){captureGuide();return;}
 if(action==='toggle-overlay'){videoState.overlay=!videoState.overlay;el.textContent=videoState.overlay?'隐藏骨架':'显示骨架';el.setAttribute('aria-pressed',String(videoState.overlay));return;}
 if(action==='retry-job'){const id=videoState.job?.jobId||videoState.job?.id;if(id)pollVideo(id);return;}
 if(action==='new-video'){clearVideo();render();return;}if(action==='refresh-videos'){await refresh();return;}
 if(action==='export'){exportData();return;}
 if(action==='privacy'){showSheet(`<h2>你的记录，始终由你掌控</h2><p class="textbody">上传视频在你连接的 Pivot 服务上进行真实动作分析，转换为无声回放视频，保存最多 7 天。原始模型观察与人工校正分别保存；不会将计数直接作为训练处方。</p><ul><li>训练页可逐条删除视频，记录页可编辑或删除训练反馈。</li><li>删除视频后，关联训练记录保留结构化观察，但不再提供视频回放。</li><li>可导出个人计划与训练记录，导出文件不包含视频。</li><li>应用不会离线缓存你的个人档案、训练 API 响应或视频。仅应用界面可离线打开。</li></ul><p class="micro">穿戴记录仅在你导入并授权后使用，可在设备页撤销。当前浏览器拥有独立空间；清除浏览器数据会丢失此空间的访问入口，请提前导出。</p>`);return;}
 if(action==='logout'){try{await api('auth/logout',{});clearVideo();setPending(null);taskInput='';answerInput='';answerTaskId='';persistDraftInput();state=null;auth={authenticated:false,pairingRequired:true};render();notify('已退出这台设备。');}catch(e){notify(e.message);}return;}
});
document.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;const form=event.target,control=event.submitter||form.querySelector('button:not([type])'),data=new FormData(form);
 if(form.id==='pair-form'){busy=true;control.disabled=true;try{await api('auth/pair',{code:String(data.get('code'))});form.elements.code.value='';auth=await api('auth');state=await api('state');loadingError='';render();}catch(e){displayError(e,form);}finally{busy=false;if(control.isConnected)control.disabled=false;}return;}
 if(form.id==='task-form'){const input=String(data.get('input')||'').trim();if(!input)return;await mutation('tasks',{input},control,()=>{taskInput='';answerInput='';answerTaskId='';persistDraftInput();go('task/'+state.activeTask.id);});return;}
 if(form.id==='answer-form'){const text=String(data.get('text')||'').trim();if(text)await mutation('answer',{id:currentTask().id,text},control,()=>{answerInput='';answerTaskId='';persistDraftInput();});return;}
 if(form.id==='confirm-form'){confirmTask(form,control);return;}
 if(form.id==='plan-form'){await mutation('plan',{expectedVersion:Number(form.dataset.version),title:String(data.get('title')).trim(),date:data.get('date'),time:data.get('time'),minutes:Number(data.get('minutes')),purpose:String(data.get('purpose')||''),content:String(data.get('content')||''),equipment:String(data.get('equipment')||'')},control,()=>{closeSheet();notify('训练计划已更新。');});return;}
 if(form.id==='profile-form'){await mutation('settings',{profile:Object.fromEntries(['goal','sport','preferredTime','constraint'].map(k=>[k,String(data.get(k)||'').trim()])),goalContext:Object.fromEntries(['endDate','eventName','eventDate'].map(k=>[k,String(data.get(k)||'').trim()]))},control,()=>{closeSheet();notify('个人档案已保存。');});return;}
 if(form.id==='alternatives-form'){const items=[...form.querySelectorAll('.altrow')].map(row=>({...(row.dataset.id?{id:row.dataset.id}:{}),title:row.querySelector('[name=title]').value.trim(),minutes:Number(row.querySelector('[name=minutes]').value),purpose:row.querySelector('[name=purpose]').value,content:row.querySelector('[name=content]').value,equipment:row.querySelector('[name=equipment]').value,intensity:row.querySelector('[name=intensity]').value}));await mutation('alternatives',{items},control,()=>{closeSheet();notify('替代方案已更新。');});return;}
 if(form.id==='weekly-form'){await mutation('settings',{weeklyGoal:Number(data.get('goal'))},control,()=>notify('每周目标已保存。'));return;}
 if(form.id==='permission-form'){await mutation('settings',{permissions:{...state.permissions,device:data.has('device'),save:data.has('save')}},control,()=>notify('权限已保存。'));return;}
 if(form.id==='upload-form'){uploadVideo(form);return;}
 if(form.id==='session-form'){
  const payload={completion:data.get('completion'),minutes:Number(data.get('minutes')),feeling:data.get('feeling'),discomfort:data.has('discomfort'),note:String(data.get('note')||'').trim(),performedAt:data.get('performedAt'),exercise:data.get('exercise')||'general',exerciseName:exerciseName(data.get('exercise')||'general'),sets:Number(data.get('sets')||1),reps:Number(data.get('reps')||0),weight:Number(data.get('weight')||0)};
  if(!Object.prototype.hasOwnProperty.call(completionNames,payload.completion)){displayError(new Error('请选择本次的实际完成情况。'),form);return;}
  if(payload.completion!=='not_done'&&payload.minutes<=0){displayError(new Error('完成或部分完成时，请填写大于 0 的实际分钟数。'),form);return;}
  if(payload.completion==='not_done')payload.minutes=0;
  if(form.dataset.video){const raw=String(data.get('correctedCount')||'').trim();payload.correctedCount=raw===''?null:Number(raw);payload.correctionReason=String(data.get('correctionReason')||'').trim();const original=form.dataset.sourceCount===''?null:Number(form.dataset.sourceCount);if(payload.correctedCount!==original&&!payload.correctionReason){displayError(new Error('修改观察次数时，请填写人工核对的原因。'),form);return;}}
  const updating=!!form.dataset.id;if(updating){payload.id=form.dataset.id;payload.expectedRevision=Number(form.dataset.revision);}else{if(form.dataset.task||data.get('linkTask'))payload.taskId=form.dataset.task||data.get('linkTask');if(form.dataset.video)payload.videoJobId=form.dataset.video;payload.idempotencyKey=recordFormKey;}
  const quickBasketball=form.hasAttribute('data-quick-basketball');
  const saved=await mutation(updating?'sessions/update':'sessions',payload,control,()=>{
   if(quickBasketball)return;
   const id=state.savedSessionId||form.dataset.id;closeSheet();notify('实际训练记录已保存。');go(id?'session/'+id:'history');
  });
  if(saved&&quickBasketball){
   const card=$('.weekly-activity');
   const summary=card?.querySelector('summary');
   if(card)card.open=true;
   if(summary&&$('#sheet').open)sheetOpener=summary;
   closeSheet();
   summary?.scrollIntoView({block:'center'});
   notify('篮球记录已保存。');
  }
  return;
 }
});
document.addEventListener('click',event=>{
 const button=event.target.closest('button');
 clickedSheetOpener=button&&!$('#sheet').open?button:null;
},true);
window.addEventListener('click',()=>{clickedSheetOpener=null;});
$('#sheet').addEventListener('close',()=>{
 if($('#sheet').open)return;
 const opener=sheetOpener,openedAt=sheetOpenedAt;
 sheetOpener=null;sheetOpenedAt='';
 if(openedAt!==location.hash)return;
 const target=opener?.isConnected&&opener!==document.body?opener:$('#main');
 target.focus({preventScroll:true});
});
window.addEventListener('hashchange',()=>{closeSheet();render();window.scrollTo(0,0);$('#main').focus({preventScroll:true});});
window.addEventListener('offline',()=>{$('#offline').hidden=false;syncConfirmationControls();notify('当前离线，本次输入仍保留，尚未保存。');});
window.addEventListener('online',()=>{$('#offline').hidden=true;syncConfirmationControls();notify('连接已恢复，可继续操作。');if(!state)void boot();else if(pendingConfirmation)void checkOperation();});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstall=event;});
window.addEventListener('appinstalled',()=>{deferredInstall=null;notify('Pivot 已添加到主屏幕。');});
if('serviceWorker' in navigator&&isSecureContext){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
boot();
