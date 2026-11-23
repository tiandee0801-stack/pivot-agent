/* Step-by-step workouts. Confirmed progress comes from the current visitor state. */
'use strict';

const workoutStatuses = {pending:'待做',completed:'已做',skipped:'已跳过'};
const workoutStorageKey = 'pivot-workout-form';
const workoutActionFields = ['sets','reps','weight','seconds','distanceMeters','rounds'];
const workoutUnits = {sets:'组',reps:'次',weight:'kg',seconds:'秒',distanceMeters:'米',rounds:'回合'};
let workoutBrowser = null;
let workoutTimerTick = null;
let workoutNotice = '';

function readWorkoutBrowser(workout) {
 if (workoutBrowser?.id === workout.id) return workoutBrowser;
 try {
  const saved = JSON.parse(sessionStorage.getItem(workoutStorageKey) || 'null');
  if (saved?.id === workout.id) return workoutBrowser = saved;
 } catch {}
 return workoutBrowser = {id:workout.id, index:null, drafts:{}, finish:{}};
}

function preserveWorkoutBrowser() {
 try {sessionStorage.setItem(workoutStorageKey, JSON.stringify(workoutBrowser));} catch {}
}

function clearWorkoutBrowser() {
 workoutBrowser = null;
 try {sessionStorage.removeItem(workoutStorageKey);} catch {}
}

function workoutCounts(actions) {
 const completed = actions.filter(action=>action.status === 'completed').length;
 const skipped = actions.filter(action=>action.status === 'skipped').length;
 return {completed, skipped, pending:actions.length-completed-skipped};
}

function workoutLocalAction(workout, index) {
 const browser = readWorkoutBrowser(workout);
 const action = workout.actions[index];
 const origin = JSON.stringify([action.status,action.entry,action.reason]);
 const saved = browser.drafts[index];
 if (saved?.origin === origin) return saved;
 return browser.drafts[index] = {origin, fields:{}};
}

function workoutIndex(workout) {
 const current = readWorkoutBrowser(workout).index;
 if (Number.isInteger(current) && current >= 0 && current < workout.actions.length) return current;
 const pending = workout.actions.findIndex(action=>action.status === 'pending');
 return pending >= 0 ? pending : 0;
}

function workoutActualSummary(entry) {
 return workoutActionFields.filter(key=>entry?.[key]!=null).map(key=>`${entry[key]} ${workoutUnits[key]}`).join(' · ');
}

function nextWorkoutCard() {
 const workout = state?.activeWorkout;
 const task = state.activeTask;
 const plan = state.plan;
 const latest = state.sessions?.find(session=>session.workoutPlanVersion === plan?.version && session.workoutId);
 let title, detail, cta;
 if (workout?.actions?.length) {
  title = workout.title;
  const {completed,skipped} = workoutCounts(workout.actions);
  detail = `训练进行中 · 已做 ${completed}/${workout.actions.length} 项${skipped?` · 跳过 ${skipped} 项`:''}`;
  cta = '<button class="btn primary" data-workout="resume" data-nav="training/workout" type="button">继续训练</button>';
 } else if (task && task.original?.version === plan?.version && ['draft','needs_info'].includes(task.status)) {
  title = '训练调整待确认';
  detail = task.input;
  cta = `<button class="btn primary" data-nav="task/${esc(task.id)}" type="button">${task.status==='draft'?'继续比较方案':'继续补充条件'}</button>`;
 } else if (latest) {
  title = latest.workoutTitle || plan.title;
  detail = `${latest.completion==='partial'?'部分完成已记录':'训练已记录'} · ${dateLabel(latest.performedAt)} · ${latest.minutes} 分钟`;
  cta = `<button class="btn soft" data-workout="summary" data-nav="session/${esc(latest.id)}" type="button">查看记录</button>`;
 } else if (plan?.actions?.length) {
  title = plan.title;
  detail = `${dateLabel(plan.date)} ${plan.time || ''} · ${plan.minutes} 分钟 · ${plan.actions.length} 个动作`;
  cta = '<button class="btn primary" data-workout="start" type="button">开始训练</button>';
 } else {
  title = '选一套开始';
  detail = '从居家、健身房和球场模板中选出下一次训练。';
  cta = '<button class="btn soft" data-nav="training/templates" type="button">选训练模板</button>';
 }
 return `<section class="workout-next" aria-labelledby="workout-next-title">
  <h2 id="workout-next-title">下一步训练</h2>
  <div class="workout-next-body"><div><h3>${esc(title)}</h3><p>${esc(detail||'')}</p></div>${cta}</div>
  ${workoutNotice?`<p class="error" role="status">${esc(workoutNotice)}</p>`:''}
 </section>`;
}

function workoutDemoStrip() {
 const choices = ['squat','side_plank','lateral_lunge'].map(catalogExercise)
  .filter(exercise=>exercise && /^\/assets\/demos\/[\w.-]+\.(?:jpg|jpeg|png|webp)$/.test(catalogDemo(exercise.id)?.poster));
 if (!choices.length) return '';
 return `<section class="workout-demos" aria-labelledby="workout-demos-title">
  <div class="workout-section-title"><h2 id="workout-demos-title">看动作示范</h2><button class="linkbtn" type="button" data-workout="demos">查看全部 ${icon('chev')}</button></div>
  <div class="workout-demo-grid">${choices.map(exercise=>`<button class="workout-demo-tile" type="button" data-catalog="details" data-id="${esc(exercise.id)}"><span><img src="${esc(catalogDemo(exercise.id).poster)}" alt="" loading="lazy">${icon('video')}</span><strong>${esc(exercise.name)}</strong></button>`).join('')}</div>
 </section>`;
}

function weeklyActivityCard() {
 const {dates} = weekStats();
 const otherSports = manualSports.filter(sport=>!['basketball','general'].includes(sport.id));
 const records = (state.sessions || []).filter(session=>
  dates.includes(session.performedAt) && session.minutes > 0 && ['completed','partial'].includes(session.completion)
  && !session.note?.startsWith('[示例体验反馈]') && session.exerciseName !== '示例训练反馈'
  && !otherSports.some(sport=>sport.id === session.exercise)
 );
 records.sort((a,b)=>b.performedAt.localeCompare(a.performedAt) || String(b.createdAt || '').localeCompare(a.createdAt || ''));
 const basketball = records.filter(session=>session.exercise === 'basketball').length;
 const countLabel = records.length ? `体能 ${records.length-basketball} 次 · 篮球 ${basketball} 场` : '本周暂无训练记录';
 const event = state.goalContext;
 const hasGame = state.profileConfirmed && upcoming() && /篮球|球局|约球|打球|basketball/i.test(event.eventName);

 return `<details class="weekly-activity">
  <summary class="weekly-activity-summary">
   <span class="weekly-activity-heading">${icon('today')}<strong>本周训练与球局</strong></span>
   <span class="weekly-activity-count">${countLabel}</span>${icon('chev')}
  </summary>
  <div class="weekly-activity-body">
   ${records.length?`<ol class="weekly-activity-list">${records.map(session=>{
    const title = session.workoutTitle || session.exerciseName || session.observation?.exerciseName || '体能训练';
    const weekday = '周' + '一二三四五六日'[dates.indexOf(session.performedAt)];
    return `<li><button class="weekly-activity-record" type="button" data-nav="session/${esc(session.id)}">
     <time datetime="${esc(session.performedAt)}">${weekday}</time>
     <span><strong>${esc(title)}</strong><small>${esc(session.minutes)} 分钟 · ${esc(completionNames[session.completion])}</small></span>${icon('chev')}
    </button></li>`;
   }).join('')}</ol>`:'<p class="weekly-activity-empty">刚打完球？记下这次的用时和感受。</p>'}
   ${hasGame?`<div class="weekly-activity-game"><span>下场球局</span><strong>${esc(event.eventName)} · <time datetime="${esc(event.eventDate)}">${esc(dateLabel(event.eventDate))}</time></strong></div>`:''}
   <button class="btn soft weekly-activity-log" type="button" data-action="quick-log-basketball">${icon('edit')} 记一场篮球</button>
  </div>
 </details>`;
}

function workoutActionProgress(actions, index) {
 return `<details class="workout-movements" ${actions[index]?.status === 'pending' ? '' : 'open'}>
  <summary>动作清单 <small>${actions.length} 项</small></summary>
  <ol>${actions.map((action,i)=>`<li><button type="button" data-workout="select" data-index="${i}" ${i===index?'aria-current="step"':''}>
   <span class="workout-step-number">${i+1}</span><span class="workout-step-name">${esc(action.exerciseName)}${action.reason?`<small>${esc(action.reason)}</small>`:''}</span><span class="workout-status" data-status="${esc(action.status)}">${esc(workoutStatuses[action.status] || '待核对')}</span>
  </button></li>`).join('')}</ol>
 </details>`;
}

function workoutView() {
 const back = `<button class="back" type="button" data-workout="pause" data-nav="training">${icon('back')}返回训练</button>`;
 const workout = state.activeWorkout;
 if (!workout?.actions?.length) {
  return `${back}<section class="card workout-next"><h1>训练进行中</h1><p>从下一步训练选择计划，开始后可在这里继续。</p><button class="btn soft" type="button" data-nav="training">查看下一步训练</button></section>`;
 }
 const index = workoutIndex(workout);
 const action = workout.actions[index];
 const draft = workoutLocalAction(workout,index);
 const {completed,skipped,pending} = workoutCounts(workout.actions);
 const planned = `${action.sets} 组 × ${action.quantity} ${catalogUnits[action.metric] || ''}`;
 const pendingFinish = readWorkoutBrowser(workout).pendingFinish;
 const demo = catalogDemo(action.exerciseId);
 const values = {...action.entry,...draft.fields};
 const running = !!draft.timer?.startedAt;
 if (running) setTimeout(syncWorkoutTimer,0);
 return `${back}<div class="workout-page">
  <section class="workout-header">
   <h1>训练进行中</h1><p>${esc(workout.title)}</p>
   <div class="workout-progress-header"><span>已做 ${completed}/${workout.actions.length} 项</span><span>${skipped?`已跳过 ${skipped} 项 · `:''}待做 ${pending} 项</span></div>
   <progress max="${workout.actions.length}" value="${completed+skipped}" aria-label="已处理的训练动作"></progress>
  </section>
  ${workoutNotice?`<p class="notice warn" role="status">${esc(workoutNotice)}</p>`:''}
  ${pendingFinish?'<p class="notice warn">上次保存结果尚未核对。</p>':''}
  <section class="workout-step">
   <div class="workout-step-header"><span>动作 ${index+1}/${workout.actions.length}</span><span class="workout-status" data-status="${esc(action.status)}">${esc(workoutStatuses[action.status] || '待核对')}</span></div>
   <h2 id="workout-action-heading" tabindex="-1">${esc(action.exerciseName)}</h2>
   <p class="workout-planned">计划 ${esc(planned)}${action.restSeconds?` · 组间休息 ${esc(action.restSeconds)} 秒`:''}</p>
   ${demo?'<button class="linkbtn workout-watch" type="button" data-workout="view-demo">播放动作示范</button>':''}
   <form id="workout-action-form" data-index="${index}" data-id="${esc(workout.id)}" data-revision="${esc(workout.revision)}">
    <fieldset><legend>填实际完成量</legend>
      ${action.metric==='time'?workoutTimerPanel(draft.timer):''}
      <div class="formgrid workout-fields">${catalogActualFields(values,action.metric)}</div>
    </fieldset>
    ${errorBox()}
    <div class="workout-step-controls">
     <button class="btn soft" type="button" data-workout="skip">${action.status==='skipped'?'修改跳过原因':'跳过此项'}</button>
     <button class="btn primary" type="submit" data-workout-save ${running||pendingFinish?'disabled':''}>${action.status==='completed'?'更新此项':'保存并继续'} ${icon('arrow')}</button>
    </div>
   ${action.status==='skipped'?'<button class="linkbtn workout-undo-skip" type="button" data-workout="undo-skip">撤销跳过</button>':''}
   </form>
  </section>
  ${workoutActionProgress(workout.actions,index)}
  <section class="workout-bottom">
   <button class="btn soft wide" type="button" data-workout="review" ${completed?'':'disabled'}>${pendingFinish?'核对保存状态':'结束并核对记录'} ${icon('chev')}</button>
   ${!completed?'<p class="micro">保存至少一个已做动作后，即可结束并核对。</p>':''}
   <div class="workout-bottom-links"><button class="linkbtn" type="button" data-workout="pause" data-nav="training">稍后继续</button><button class="linkbtn" type="button" data-workout="discard">放弃本次训练</button></div>
  </section>
 </div>`;
}

function workoutTimerMilliseconds(timer) {
 return (timer?.elapsed || 0) + (timer?.startedAt ? Math.max(0,Date.now()-timer.startedAt) : 0);
}

function workoutTimerLabel(timer) {
 const seconds = Math.floor(workoutTimerMilliseconds(timer)/1000);
 return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}

function workoutTimerPanel(timer) {
 return `<div class="workout-timer"><output id="workout-timer-value" aria-label="已计时">${workoutTimerLabel(timer)}</output>
  <button class="btn soft" type="button" data-workout="timer">${timer?.startedAt?'停止计时':timer?.elapsed?'继续计时':'开始计时'}</button>
 </div>`;
}

function syncWorkoutTimer() {
 clearTimeout(workoutTimerTick);
 const output = $('#workout-timer-value');
 const workout = state?.activeWorkout;
 if (!output || !workout) return;
 const timer = workoutLocalAction(workout,workoutIndex(workout)).timer;
 output.textContent = workoutTimerLabel(timer);
 if (timer?.startedAt) workoutTimerTick = setTimeout(syncWorkoutTimer,250);
}

function stopWorkoutTimer(workout,index) {
 const draft = workoutLocalAction(workout,index);
 if (!draft.timer?.startedAt) return;
 const elapsed = workoutTimerMilliseconds(draft.timer);
 draft.timer = {elapsed};
 const seconds = Math.floor(elapsed/1000);
 if (seconds > 0 && seconds <= catalogMetricMaximums.time) draft.fields.seconds = String(seconds);
 preserveWorkoutBrowser();
}

function toggleWorkoutTimer(control,workout,index) {
 const draft = workoutLocalAction(workout,index);
 const form = control.form;
 const closing = !!draft.timer?.startedAt;
 if (closing) {
  stopWorkoutTimer(workout,index);
  if (draft.fields.seconds != null) form.elements.seconds.value=draft.fields.seconds;
 } else {
  draft.timer = {elapsed:draft.timer?.elapsed||0,startedAt:Date.now()};
 }
 preserveWorkoutBrowser();
 control.textContent = closing ? '继续计时' : '停止计时';
 form.querySelector('[data-workout-save]').disabled = !closing || !!readWorkoutBrowser(workout).pendingFinish;
 syncWorkoutTimer();
}

function workoutSkipSheet(workout,index) {
 const action = workout.actions[index];
 const draft = workoutLocalAction(workout,index);
 showSheet(`<h2>跳过${esc(action.exerciseName)}</h2>
  <form id="workout-skip-form" data-index="${index}" data-id="${esc(workout.id)}" data-revision="${esc(workout.revision)}">
   <label class="field">跳过原因（选填）<textarea name="reason" rows="2" maxlength="120">${esc(draft.reason ?? action.reason ?? '')}</textarea></label>
   ${errorBox()}<button class="btn primary wide" type="submit">确认跳过</button>
  </form>`);
}

function workoutFinishSheet(workout) {
 const browser = readWorkoutBrowser(workout);
 const pending = browser.pendingFinish;
 const fields = pending?.payload || browser.finish;
 const {completed,skipped,pending:remaining} = workoutCounts(workout.actions);
 showSheet(`<h2>核对本次训练</h2>
  <p class="micro">已做 ${completed} 项 · 跳过 ${skipped} 项 · 待做 ${remaining} 项</p>
  ${skipped+remaining?`<p class="notice">将保存为部分完成，记录已做动作和当前进度。</p>`:''}
  <ol class="workout-summary-list">${workout.actions.map(action=>`<li><strong>${esc(action.exerciseName)}</strong><div><span class="workout-status" data-status="${esc(action.status)}">${esc(workoutStatuses[action.status] || '待核对')}</span>${action.entry||action.reason?`<small>${esc(action.reason||workoutActualSummary(action.entry))}</small>`:''}</div></li>`).join('')}</ol>
  <form id="workout-finish-form" data-id="${esc(workout.id)}" data-revision="${esc(workout.revision)}">
   ${pending?'<p class="notice warn">上次保存结果尚未核对。联网后可核对并保存同一条记录。</p>':''}
   <fieldset ${pending?'disabled':''}><legend>确认实际训练</legend>
    <div class="formgrid">
     ${catalogNumberField('实际训练分钟','minutes',fields.minutes,1,240)}
     <label class="field">训练感受<select name="feeling" required><option value="">请选择</option>${catalogFilterOptions(['合适','偏累','偏轻松','不合适'].map(item=>[item,item]),fields.feeling)}</select></label>
    </div>
    <label class="check"><input type="checkbox" name="discomfort" ${fields.discomfort?'checked':''}>训练中出现了身体不适</label>
    <label class="field">训练备注（选填）<textarea name="note" rows="2" maxlength="450">${esc(fields.note||'')}</textarea></label>
   </fieldset>
   ${errorBox()}
   <button class="btn primary wide" type="submit" ${completed?'':'disabled'}>${pending?'核对并保存':'确认并保存训练'} ${icon('check')}</button>
  </form>`);
}

function workoutDiscardSheet(workout) {
 showSheet(`<h2>放弃本次训练？</h2>
  <p class="textbody">本次进行中的进度会清除，已保存的训练计划仍可再次开始。</p>
  <form id="workout-discard-form" data-id="${esc(workout.id)}" data-revision="${esc(workout.revision)}">
   ${errorBox()}<div class="workout-step-controls">
    <button class="btn soft" type="button" data-action="close-sheet">继续保留进度</button>
    <button class="btn danger" type="submit">确认放弃</button>
   </div>
  </form>`);
}

function workoutHistoryOutcomes(session) {
 const outcomes = session.workoutActions?.filter(action=>action.status !== 'completed') || [];
 if (!outcomes.length) return '';
 return `<section class="card catalog-history"><h2>跳过与待做</h2><ol class="catalog-action-list">
  ${outcomes.map(action=>`<li><strong>${esc(action.exerciseName)}</strong><small>${esc(workoutStatuses[action.status]||'待核对')}${action.reason?` · ${esc(action.reason)}`:''}</small></li>`).join('')}
 </ol></section>`;
}

function workoutFailure(control,error) {
 const form = control.closest('form');
 const box = form?.querySelector('.error');
 if (!box) {workoutNotice=error.message;render();return;}
 box.textContent = error.message;
 if (error.transport || ['stale_workout','workout_not_found','stale_plan'].includes(error.code)) {
  box.insertAdjacentHTML('beforeend','<div><button class="linkbtn" type="button" data-workout="sync">读取最新进度</button></div>');
 }
}

function workoutFinishSaved(id) {
 clearWorkoutBrowser();
 closeSheet();
 workoutNotice='';
 notify('本次训练已保存。');
 go(id?'session/'+id:'history');
}

async function workoutRequest(control,path,payload,success,before) {
 if (busy) return;
 busy=true;
 const label=control.innerHTML;
 const inlineError=control.closest('form')?.querySelector('.error');
 if (inlineError) inlineError.textContent='';
 control.disabled=true;
 control.textContent='正在保存…';
 try {
  if (before && await before()) return;
  state=await api(path,payload);
  workoutNotice='';
  success();
  render();
 } catch(error) {
  if (path==='workout/finish') {
   if (error.transport) {
    const workout = state.activeWorkout;
    if (workout?.id===payload.id) workoutFinishSheet(workout);
    const next = $('#workout-finish-form button[type=submit]');
    workoutFailure(next||control,error);
   } else {
    if (workoutBrowser) {
     delete workoutBrowser.pendingFinish;
     preserveWorkoutBrowser();
    }
    if (state.activeWorkout && control.form?.elements.minutes?.matches(':disabled')) {
     workoutFinishSheet(state.activeWorkout);
    }
    workoutFailure($('#workout-finish-form button[type=submit]')||control,error);
   }
  } else workoutFailure(control,error);
 } finally {
  busy=false;
  if (control.isConnected) {control.disabled=false;control.innerHTML=label;}
 }
}

function workoutActionSaved(index,status) {
 const workout=state.activeWorkout;
 const browser=readWorkoutBrowser(workout);
 delete browser.drafts[index];
 if (status !== 'pending') {
  const after=workout.actions.findIndex((action,i)=>i>index&&action.status==='pending');
  const first=workout.actions.findIndex(action=>action.status==='pending');
  browser.index=after>=0?after:first>=0?first:index;
 }
 preserveWorkoutBrowser();
 closeSheet();
 setTimeout(()=>$('#workout-action-heading')?.focus(),0);
}

function saveWorkoutFields(form) {
 const workout=state?.activeWorkout;
 if (!workout || form?.dataset.id!==workout.id) return;
 if (form.id==='workout-action-form') {
  const draft=workoutLocalAction(workout,Number(form.dataset.index));
  draft.fields=Object.fromEntries(workoutActionFields.filter(name=>form.elements[name]).map(name=>[name,form.elements[name].value]));
 } else if (form.id==='workout-skip-form') {
  workoutLocalAction(workout,Number(form.dataset.index)).reason=form.elements.reason.value;
 } else if (form.id==='workout-finish-form') {
  if (readWorkoutBrowser(workout).pendingFinish) return;
  readWorkoutBrowser(workout).finish={
   minutes:form.elements.minutes.value,feeling:form.elements.feeling.value,
   discomfort:form.elements.discomfort.checked,note:form.elements.note.value,
  };
 } else return;
 preserveWorkoutBrowser();
}

document.addEventListener('input',event=>saveWorkoutFields(event.target.form));
document.addEventListener('change',event=>saveWorkoutFields(event.target.form));

document.addEventListener('click',async event=>{
 const control=event.target.closest('button[data-workout]');
 if (!control||busy) return;
 const action=control.dataset.workout;
 const workout=state.activeWorkout;
 if (action==='demos') {
  Object.assign(catalogFilters,{query:'',equipment:'',space:'',demo:true});
  preserveCatalogView();
  go('training/library');
 }
 if (action==='start') {
  await workoutRequest(control,'workout/start',{planVersion:state.plan.version},()=>go('training/workout'));
 }
 if (action==='sync') {
  busy=true;
  control.disabled=true;
  try {
   state=await api('state');
   if (!state.activeWorkout && workout) {
    const saved=state.sessions?.find(session=>session.workoutId===workout.id);
    if (saved) {workoutFinishSaved(saved.id);return;}
   }
   workoutNotice='已读取最新训练进度。';
   closeSheet();
   render();
  } catch(error) {workoutFailure(control,error);}
  finally {busy=false;if(control.isConnected)control.disabled=false;}
 }
 if (!workout) return;
 const index=workoutIndex(workout);
 if (action==='pause') stopWorkoutTimer(workout,index);
 if (action==='select') {
  stopWorkoutTimer(workout,index);
  readWorkoutBrowser(workout).index=Number(control.dataset.index);
  preserveWorkoutBrowser();
  workoutNotice='';
  render();
  $('#workout-action-heading')?.focus();
 }
 if (action==='skip') {
  if (readWorkoutBrowser(workout).pendingFinish) {workoutFinishSheet(workout);return;}
  workoutSkipSheet(workout,index);
 }
 if (action==='undo-skip' && !readWorkoutBrowser(workout).pendingFinish) {
  const payload={id:workout.id,expectedRevision:workout.revision,index,status:'pending'};
  await workoutRequest(control,'workout/action',payload,()=>workoutActionSaved(index,'pending'));
 }
 if (action==='review') workoutFinishSheet(workout);
 if (action==='discard') {
  if (readWorkoutBrowser(workout).pendingFinish) {workoutFinishSheet(workout);return;}
  workoutDiscardSheet(workout);
 }
 if (action==='timer') toggleWorkoutTimer(control,workout,index);
 if (action==='view-demo') {
  const exercise=catalogExercise(workout.actions[index].exerciseId);
  if (exercise) showSheet(`<h2>${esc(exercise.name)}</h2>${catalogDemoSection(exercise)}`);
 }
});

document.addEventListener('submit',async event=>{
 const {target:form,submitter}=event;
 if (!['workout-action-form','workout-skip-form','workout-finish-form','workout-discard-form'].includes(form.id)) return;
 event.preventDefault();
 if (busy || !state?.activeWorkout) return;
 const control=submitter||form.querySelector('button[type=submit]');
 const workout=state.activeWorkout;
 const base={id:form.dataset.id,expectedRevision:Number(form.dataset.revision)};
 if (form.id==='workout-action-form'||form.id==='workout-skip-form') {
  if (readWorkoutBrowser(workout).pendingFinish) return;
  const index=Number(form.dataset.index);
  saveWorkoutFields(form);
  const status=form.id==='workout-skip-form'?'skipped':'completed';
  const entry={exerciseId:workout.actions[index].exerciseId};
  if (status==='completed') {
   if (workoutLocalAction(workout,index).timer?.startedAt) return;
   for (const name of workoutActionFields) {
    const field=form.elements[name];
    if (field && field.value!=='') entry[name]=Number(field.value);
   }
  }
  const extra=status==='completed'?{entry}:{reason:form.elements.reason.value.trim()};
  await workoutRequest(control,'workout/action',{...base,index,status,...extra},()=>workoutActionSaved(index,status));
 }
 if (form.id==='workout-finish-form') {
  const browser=readWorkoutBrowser(workout);
  const existing=browser.pendingFinish;
  saveWorkoutFields(form);
  const fields=browser.finish;
  const payload=existing?.payload||{...base,minutes:Number(fields.minutes),feeling:fields.feeling,
   discomfort:!!fields.discomfort,note:(fields.note||'').trim(),idempotencyKey:uid()};
  browser.pendingFinish={payload};
  preserveWorkoutBrowser();
  const checkExisting=existing?async()=>{
   const current=await api('state');
   const saved=current.sessions?.find(session=>session.workoutId===workout.id);
   if (saved) {state=current;workoutFinishSaved(saved.id);return true;}
   return false;
  }:null;
  await workoutRequest(control,'workout/finish',payload,()=>workoutFinishSaved(state.savedSessionId),checkExisting);
 }
 if (form.id==='workout-discard-form') {
  await workoutRequest(control,'workout/discard',base,()=>{
   clearWorkoutBrowser();closeSheet();notify('已放弃本次训练。');go('training');
  });
 }
});
