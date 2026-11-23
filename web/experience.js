/* Mobile experience built on the shared task and persistence flow. */
const baseTaskView = taskView;
const baseTrainingView = trainingView;
const baseDevicesView = devicesView;
const baseSettingsView = settingsView;
const baseSessionView = sessionView;
let feedbackKey = '';

const quickScenarios = {
 short: {title:'只有 30 分钟', description:'精简今天的训练', icon:'clock'},
 ball: {title:'临时约了球', description:'协调力量与球局', icon:'today'},
 tired: {title:'训练状态变化', description:'按今天的感受调整', icon:'watch'},
};
const sampleMode = () => !!state?.experience && !state.profileConfirmed && state.planIsExample;
const upcoming = () => state.goalContext?.eventName && state.goalContext.eventDate >= todayISO();
const activityCaption = () => upcoming()
 ? `${state.goalContext.eventDate.slice(5).replace('-','/')} · ${state.goalContext.eventName}`
 : '未设置近期球局';

function weekRibbon() {
 const {dates,done}=weekStats();
 return `<div class="week-ribbon">${dates.map((date,index)=>`
  <button class="week-day ${date===state.plan.date?'selected':''} ${date===todayISO()?'is-today':''}"
   data-exp="day" data-value="${esc(date)}" aria-label="${esc(date)}">
   <span>${'一二三四五六日'[index]}</span><b>${Number(date.slice(-2))}</b>
   <i class="${done.has(date)?'done':date===state.plan.date?'strength':date===state.goalContext?.eventDate?'ball':''}"></i>
  </button>`).join('')}</div>`;
}

function stateCards() {
 const real = state.permissions.device && (state.device.metrics || []).length;
 const metrics = real ? state.device.metrics.slice(0,3) : sampleMode() ? state.experience.metrics : [];
 return `<div class="sectionhead"><h2>穿戴与身体状态</h2>
  <button class="linkbtn" data-nav="devices">${real?'记录来源':metrics.length?'示例数据':'添加记录'} ${icon('chev')}</button></div>
  ${metrics.length?`<div class="state-cards">${metrics.map((metric,index)=>`
   <button class="state-tile t${index}" data-exp="metric" data-value="${index}">
    <span>${esc(metric.label)}</span><b>${esc(metric.value)}<small>${esc(metric.unit)}</small></b>
    <span class="metric-rule" aria-hidden="true"></span>
    <small>${real?(metric.fresh===false?'历史记录':'已导入记录'):'示例 · 非设备实测'}</small>
   </button>`).join('')}</div>`:
  `<button class="card quick-record wide" data-nav="devices">${icon('watch')}
   <span class="rowmain"><strong>带上你的穿戴记录</strong><small>Apple 健康 / Garmin 文件导入</small></span>${icon('chev')}</button>`}`;
}

function todayView() {
 const plan = state.plan;
 const task = state.activeTask;
 const open = task && ['draft','needs_info'].includes(task.status);
 const last = (state.history || []).find(item => item.receipt?.planSaved);
 const feedback = last && (state.sessions || []).find(session => session.taskId === last.id);
 return `
  <section class="sport-deck" aria-label="运动入口">
   <button class="sport-card ball-card" data-action="edit-profile">
    <img src="/assets/court.jpg" width="1000" height="1500" alt="">
    <span class="sport-copy"><strong>球类运动</strong><small>${upcoming()?esc(state.goalContext.eventName):'设置近期球局'}</small></span>
    ${icon('arrow')}
   </button>
   <button class="sport-card strength-card" data-nav="training">
    <img src="/assets/strength.png" width="1535" height="1025" alt="">
    <span class="sport-copy"><strong>力量训练</strong><small>${state.trainingCatalog?'找动作 · 做训练':'记录动作表现'}</small></span>
    ${icon('arrow')}
   </button>
  </section>
  <div class="welcome"><h1>调一下今天的训练</h1>${sampleMode()?'<span class="experience-badge">示例计划</span>':''}</div>
  <section class="today-overview" aria-label="今天的计划和近期球局">
   <div class="overview-plan">
    <div class="plan-symbol">${icon('training')}</div>
    <div class="rowmain"><small>已保存的安排 · ${esc(plan.date===todayISO()?'今天':plan.date)} ${esc(plan.time)}</small><h2>${esc(plan.title)}</h2></div>
    <div class="time-number"><b>${esc(plan.minutes)}</b><small>分钟</small></div>
   </div>
   <dl class="overview-context">
    <div><dt>当前目标</dt><dd>${esc(state.profile.goal || plan.purpose || '尚未设置')}</dd></div>
    <div><dt>近期球局</dt><dd>${esc(activityCaption())}</dd></div>
   </dl>
   <div class="overview-actions"><button class="linkbtn" data-exp="plan-detail">训练内容 ${icon('chev')}</button>
    <button class="linkbtn" data-action="edit-plan">编辑安排 ${icon('edit')}</button></div>
   ${plan.actions?.length&&state.trainingCatalog?'<button class="btn soft wide catalog-home-record" type="button" data-catalog="record-plan">记录这套训练</button>':''}
  </section>
  <section class="adjust-card">
   <h2>${open?'接着完成这次调整':'今天有什么变化？'}</h2>
   ${open?`<p>${esc(task.input)}</p>
    <div class="actions"><button class="btn primary" data-nav="task/${esc(task.id)}">继续调整 ${icon('arrow')}</button>
     ${hasPendingConfirmation(task.id)?'':'<button class="linkbtn" data-v2="fresh-task">重新描述变化</button>'}</div>`:
   `<div class="scenario-grid">${Object.entries(quickScenarios).map(([kind,scenario])=>`
    <button data-exp="quick" data-value="${kind}"><span>${icon(scenario.icon)}</span><b>${scenario.title}</b>
     <small>${scenario.description}</small>${icon('arrow')}</button>`).join('')}</div>
    <details class="custom-request" ${taskInput?'open':''}><summary>其他变化，直接告诉 Pivot ${icon('chev')}</summary>
     <form id="task-form"><label class="hidden" for="agent-input">告诉 Pivot 你的变化</label>
      <textarea name="input" id="agent-input" maxlength="500" required placeholder="例如：今天只剩 30 分钟，只有弹力带">${esc(taskInput)}</textarea>
      ${errorBox()}<button class="btn primary wide" type="submit">调整我的计划 ${icon('arrow')}</button></form>
    </details>`}
  </section>
  ${last?`<section class="follow-card"><span class="follow-icon">${icon(feedback?'check':'note')}</span>
   <div><small>计划已保存</small><h3>${feedback?`实际：${esc(completionNames[feedback.completion])}`:'实际：执行未知'}</h3>
    <p>${feedback?`${esc(feedback.minutes)} 分钟 · ${esc(feedback.feeling)}`:'练完后可补记实际用时和感受。'}</p></div>
   <button class="round-link" ${feedback?`data-nav="session/${esc(feedback.id)}"`:`data-exp="feedback" data-value="${esc(last.id)}"`}
    aria-label="${feedback?'查看反馈':'记录练后反馈'}">${icon('arrow')}</button></section>`:''}
  <div class="experience-secondary">${weekRibbon()}
   <section class="event-banner"><img src="/assets/court.jpg" alt="阳光下的室外篮球场" loading="lazy"><div class="event-shade"></div>
    <div class="event-copy"><span class="event-label">近期球局</span><h2>${esc(upcoming()?state.goalContext.eventName:'设置重要活动')}</h2>
     <p>${esc(activityCaption())}${sampleMode()?' · 示例安排':''}</p></div>
    <button class="event-edit" data-action="edit-profile" aria-label="编辑运动目标">${icon('edit')}</button>
   </section>
  </div>
  ${stateCards()}
  <button class="video-entry" data-nav="${studioRoute()}"><div class="video-entry-icon">${icon('video')}</div>
   <span class="rowmain"><strong>记录训练视频</strong><small>上传、观察与核对</small></span>${icon('arrow')}</button>
  <div class="sectionhead"><h2>训练记录</h2><button class="linkbtn" data-nav="history">查看全部 ${icon('chev')}</button></div>
  <div class="card list">${(state.sessions||[]).slice(0,2).map(sessionRow).join('')||`
   <button class="row" data-action="add-record"><span class="rowicon">${icon('note')}</span>
    <span class="rowmain"><strong>记一笔实际训练</strong><small>计划保存与实际训练分别记录</small></span>${icon('chev')}</button>`}</div>
  <div class="home-bottom"><button class="linkbtn" data-action="edit-alternatives">管理备选方案</button><button class="linkbtn" data-exp="intro">体验说明</button></div>`;
}

function quickSheet(kind) {
 const scenario = quickScenarios[kind];
 const slots = kind === 'ball' ? `<fieldset class="quick-slots">
  <legend>新的可用时段</legend><div class="formgrid">
   <label class="field">日期<input name="date" type="date" min="${todayISO()}"></label>
   <label class="field">时间<input name="time" type="time"></label></div>
  <p class="micro">还没确定的话留空，Pivot 会补问。</p>
 </fieldset>` : `<label class="field">本次可用分钟<input type="number" name="minutes" min="1" max="240"
  inputmode="numeric" ${kind==='short'?'value="30" required placeholder="填写可用时长"':'placeholder="不确定可留空"'}></label>`;
 showSheet(`<h2>${scenario.title}</h2><p class="subtle">${scenario.description}。</p>
  <form id="quick-form" data-scenario="${kind}">
   <div class="mini-context"><span>原安排</span><strong>${esc(state.plan.title)} · ${esc(state.plan.minutes)} 分钟</strong></div>
   ${slots}
   <label class="field">本次可用器械<select name="equipment">
    <option value="">还没确定</option><option value="哑铃">有哑铃</option><option value="弹力带">只有弹力带</option>
    <option value="徒手">徒手 / 不用器械</option><option value="custom">填写其他器械</option>
   </select></label>
   <label class="field" id="quick-other-equipment" hidden>其他器械<input name="otherEquipment" maxlength="100" placeholder="例如：哑铃和训练凳" disabled></label>
   <fieldset class="feeling-field"><legend>此刻身体感觉怎么样？</legend><div class="feeling-choice">
    ${[['unknown','暂未确认'],['normal','状态正常'],['tired','有些疲劳'],['pain','有明显不适']].map(([value,label])=>`
     <label><input type="radio" name="condition" value="${value}" ${value==='unknown'?'checked':''}><span>${label}</span></label>`).join('')}
   </div></fieldset>
   ${kind==='tired'?'<label class="check"><input type="checkbox" name="sleepChanged"><span>昨晚睡眠受影响（选填）</span></label>':''}
   <label class="field">运动限制（选填）<input name="restriction" maxlength="120" placeholder="例如：不做下肢深蹲"></label>
   ${errorBox()}<button class="btn primary wide" type="submit">查看调整方案 ${icon('arrow')}</button>
  </form>`);
}

function journey(step) {
 return `<div class="journey">${['说明变化','确认安排','训练反馈'].map((label,index)=>`
  <span class="${index+1===step?'active':index+1<step?'finished':''}" ${index+1===step?'aria-current="step"':''}>
   <i aria-hidden="true">${index+1<step?'✓':index+1}</i>${label}</span>`).join('')}</div>`;
}

function ballImpact(option) {
 if (option.changes?.ballImpact) return option.changes.ballImpact;
 if (!upcoming()) return '';
 return option.date === state.goalContext.eventDate
  ? `${activityCaption()} · 当天时段是否冲突待确认`
  : `${activityCaption()} · 球局安排保持不变`;
}

function candidateRows(option, task) {
 const rescheduled = option.id === 'reschedule';
 const changed = option.changes?.changed || (rescheduled
  ? `力量训练改到 ${option.date} ${option.time}，须确认该时段有空`
  : `以 ${option.title} 替换原安排，${option.minutes} 分钟`);
 return [
  ['保留', option.changes?.retained || option.purpose],
  [rescheduled?'改期':'变更', changed],
  ['球局', ballImpact(option)],
  ['来源', option.source || task.original.source],
 ].filter(([,value])=>value).map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('');
}

function exclusions(task) {
 if (!task.excludedCandidates?.length) return '';
 return `<section class="candidate-exclusions" aria-label="未入选的备选">
  <h2>未入选的备选</h2>
  <ul>${task.excludedCandidates.map(item=>`<li><strong>${esc(item.title)}</strong><span>${esc(item.reason)}</span></li>`).join('')}</ul>
 </section>`;
}

function candidateOption(option,task,index) {
 const id = `option-${index}`;
 return `<div class="option candidate-detail">
  <input type="radio" name="optionId" id="${id}" value="${esc(option.id)}" ${option.id===selectedOption?'checked':''} required>
  <div class="candidate-copy">
   <label for="${id}" class="option-heading"><strong>${esc(option.title)}</strong><small>${option.id===selectedOption?'已选中':'备选'}</small></label>
   <p class="option-time">${schedule(option)}</p>
   <dl class="candidate-diff">${candidateRows(option,task)}</dl>
   ${option.actions?.length?catalogActionList(option.actions):''}
   ${option.content||option.reason?`<details><summary>训练内容与判断依据</summary>
    ${option.content?`<p>${esc(option.content)}</p>`:''}${option.reason?`<p>${esc(option.reason)}</p>`:''}
   </details>`:''}
  </div>
 </div>`;
}

function taskEvidence(task) {
 if (!task.evidence?.length && !task.unknowns?.length) return '';
 return `<section class="card evidence-card"><details><summary>查看本次使用的依据 ${icon('chev')}</summary>
  <ul class="evidence">${(task.evidence||[]).map(item=>`<li><strong>${esc(item.label)}</strong>
   <p>${esc(item.value)}</p><small>${esc([item.source,stamp(item.at)].filter(Boolean).join(' · '))}</small></li>`).join('')}</ul>
  ${task.unknowns?.length?`<p class="micro">${task.unknowns.map(esc).join('；')}</p>`:''}</details></section>`;
}

function taskBasketballReference(task) {
 const game = task.evidence?.find(item=>item.exercise==='basketball' && item.sessionId && item.source==='用户训练记录');
 if (!game) return '';
 const hasRecord = (state.sessions||[]).some(session=>session.id===game.sessionId);
 return `<section class="task-basketball-reference" aria-labelledby="basketball-reference-title">
  <div><h2 id="basketball-reference-title">参考的篮球记录</h2><p>${esc(game.value)}</p>
  <time datetime="${esc(game.at)}">${esc(dateLabel(game.at))}</time></div>
  ${hasRecord?`<button class="linkbtn" type="button" data-nav="session/${esc(game.sessionId)}">查看原记录 ${icon('chev')}</button>`:''}
 </section>`;
}

function rescheduleSheet(task) {
 showSheet(`<h2>另选训练时段</h2><p class="subtle">${esc(task.original.title)} · ${esc(task.original.minutes)} 分钟</p>
  <form id="reschedule-training-form" data-task="${esc(task.id)}">
   <div class="formgrid"><label class="field">日期<input name="date" type="date" min="${todayISO()}" required></label>
   <label class="field">开始时间<input name="time" type="time" required></label></div>
   ${errorBox()}<button class="btn primary wide" type="submit">查看改期方案 ${icon('arrow')}</button>
  </form>`);
}

function savedTaskView(task,feedback) {
 const plan = task.options?.find(option=>option.id===task.selectedId)||task.original;
 const impact = ballImpact(plan);
 const canStart = !feedback && plan.actions?.length && state.trainingCatalog && state.plan.version===task.receipt.planVersion;
 return `<button class="back" data-nav="today">${icon('back')}返回首页</button>${journey(feedback?3:2)}
  <section class="saved-hero"><span class="saved-check">${icon('check')}</span>
   <h1>${feedback?'训练反馈已保存':'新安排，准备好了。'}</h1>
   <p>${feedback?'实际反馈已进入你的训练记录。':'计划已保存。训练后再补实际反馈。'}</p>
  </section>
  <section class="card saved-plan">
   <div class="saved-badges"><span class="badge">计划已保存</span>
    <span class="badge neutral">${feedback?`实际：${esc(completionNames[feedback.completion])}`:'实际：执行未知'}</span></div>
   <h2>${esc(plan.title)}</h2><div class="saved-duration">${esc(plan.minutes)}<small>分钟 · ${esc(plan.date)} ${esc(plan.time)}</small></div>
   ${plan.content?`<p>${esc(plan.content)}</p>`:''}
   ${plan.actions?.length?catalogActionList(plan.actions):''}
   ${task.receipt?.operationId?`<details class="saved-receipt"><summary>保存回执</summary><p>操作编号 <code>${esc(task.receipt.operationId)}</code></p></details>`:''}
  </section>
  ${interpretationNote(task)}
  ${taskBasketballReference(task)}
  ${impact?`<div class="preserved">${icon('today')} ${esc(impact)}</div>`:''}
  ${canStart?`<button class="btn primary wide" type="button" data-nav="training">去训练页开练 ${icon('arrow')}</button>`:''}
  ${feedback?`<button class="btn primary wide" data-nav="session/${esc(feedback.id)}">查看这次反馈 ${icon('arrow')}</button>`:
  `<button class="btn ${canStart?'soft':'primary'} wide" ${plan.actions?.length&&state.trainingCatalog?`data-catalog="record-plan" data-task="${esc(task.id)}"`:`data-exp="feedback" data-value="${esc(task.id)}"`}>记录练后反馈 ${icon('arrow')}</button>
   <button class="btn soft wide" data-nav="${studioRoute()}">拍摄或上传训练视频</button>`}
  <button class="linkbtn center-link" data-nav="today">回到首页</button>`;
}

taskView = function() {
 const task = currentTask();
 if (!task) return baseTaskView();
 const back = `<button class="back" data-nav="today">${icon('back')}返回首页</button>`;
 if (task.status === 'stopped') {
  return `${back}${journey(1)}<section class="card stopped-task"><span class="badge warn">已停止自动调整</span>
   <h1>先保留原计划</h1>${interpretationNote(task)}<p>${esc(task.reason)}</p><div class="actions">
    ${button('add-record','仅记录感受','soft')}<button class="btn primary" data-nav="today">返回原计划</button>
   </div></section>${taskEvidence(task)}`;
 }
 if (task.receipt?.planSaved) {
  return savedTaskView(task,(state.sessions||[]).find(session=>session.taskId===task.id));
 }
 if (task.status !== 'draft' || !task.options?.length) {
  const needsInfo = task.status === 'needs_info';
  const fatigueBlocked = needsInfo && task.original.actions?.length && task.excludedCandidates?.some(item=>item.code==='condition');
  const answerAction = fatigueBlocked ? '<button class="btn soft" type="button" data-exp="reschedule">另选训练时段</button>' : '';
  const base = baseTaskView({reference:needsInfo?taskBasketballReference(task):'',answerAction});
  return needsInfo && !fatigueBlocked ? base + exclusions(task) : base;
 }
 if (selectedTask !== `${task.id}:${task.draftVersion}`) {
  selectedTask=`${task.id}:${task.draftVersion}`;
  selectedOption=task.options[0].id;
 }
 const option = task.options.find(item=>item.id===selectedOption) || task.options[0];
 const ownReceiptPending = hasPendingConfirmation(task.id);
 const blocked = confirmationBlocked() || !state.permissions.save;
 return `${back}${journey(2)}
  <div class="proposal-heading"><h1>比较调整方案</h1><p>${esc(task.input)}</p></div>
  ${interpretationNote(task)}
  ${taskBasketballReference(task)}
  <section class="compare-card"><div><small>原安排</small><b>${esc(task.original.minutes)}<span> 分钟</span></b><p>${esc(task.original.title)}</p></div>
   <span class="compare-arrow">${icon('arrow')}</span><div class="after"><small>选定方案</small><b>${esc(option.minutes)}<span> 分钟</span></b><p>${esc(option.title)}</p></div></section>
  ${exclusions(task)}
  <form id="confirm-form">
   <fieldset class="candidate-options"><legend>选择适合你的方案</legend>
    ${task.options.map((item,index)=>candidateOption(item,task,index)).join('')}</fieldset>
   <div id="availability-confirm" ${option.requiresAvailabilityConfirmation?'':'hidden'}>
    <label class="check"><input type="checkbox" name="availabilityConfirmed" ${option.requiresAvailabilityConfirmation?'required':'disabled'}>
     <span>${option.actions?.length && option.id !== 'reschedule' ? '我确认训练时段与球局不冲突' : '我确认这个新时段有空'}</span></label></div>
   ${!state.permissions.save?'<div class="notice warn">保存权限已关闭，请在「我的」中开启。</div>':''}
   ${errorBox()}
   <div class="confirm-actions">
    <button class="btn primary wide" type="submit" ${blocked?'disabled':''}>确认并保存 ${icon('check')}</button>
    ${ownReceiptPending?'':button('keep','保持原安排','soft wide')}
   </div>
  </form>
  ${taskEvidence(task)}
  ${ownReceiptPending?'':`<div class="draft-actions">${button('revise','重新描述变化','link')}${button('cancel','取消这次调整','link')}</div>`}
  <p class="micro center">确认前不会改变你的计划</p>`;
};

function feedbackSheet(id) {
 feedbackKey = uid();
 const already = (state.sessions||[]).find(session=>session.taskId===id);
 if (already) { go('session/'+already.id); return; }
 showSheet(`<h2>这次，练得怎么样？</h2>
  <p class="subtle">${sampleMode()?'这条记录会标为示例反馈。':'下一次调整会参考你填写的实际情况。'}</p>
  <form id="quick-feedback" data-task="${esc(id)}">
   <label class="field">完成情况<select name="completion" required>
    <option value="">请选择</option><option value="completed">已完成</option>
    <option value="partial">部分完成</option><option value="not_done">未训练</option>
   </select></label>
   <div class="formgrid">
    <label class="field">实际训练分钟<input type="number" name="minutes" min="1" max="240" inputmode="numeric" placeholder="填写实际用时" required></label>
    <label class="field">训练感受<select name="feeling" required><option value="">请选择</option>
     <option>合适</option><option>偏累</option><option>偏轻松</option><option>不合适</option>
    </select></label>
   </div>
   <label class="check"><input type="checkbox" name="discomfort"><span>训练中出现了身体不适</span></label>
   <label class="field">补充一句（选填）<textarea name="note" rows="2" maxlength="450" placeholder="例如：时间刚好，但今天腿有些疲劳"></textarea></label>
   ${errorBox()}<button class="btn primary wide" type="submit">保存${sampleMode()?'示例':''}反馈 ${icon('check')}</button>
  </form>`);
}

sessionView = function() {
 const session = currentSession();
 const linked = session && (state.history||[]).find(item=>item.id===session.taskId && item.receipt?.planSaved);
 if (!linked) return baseSessionView();
 const plan = linked.options?.find(option=>option.id===linked.selectedId) || linked.original;
 return baseSessionView() + `<section class="card session-lineage"><h2>关联的计划调整</h2>
  <p>${esc(plan.title)} · ${esc(plan.minutes)} 分钟 · 计划已保存</p>
  <button class="linkbtn" data-nav="task/${esc(linked.id)}">查看保存的安排 ${icon('chev')}</button></section>`;
};

trainingView = function() {
 return `${head('训练视频')}<div class="movement-intro"><span class="badge">5 种动作</span><p>上传、观察与核对</p></div>${baseTrainingView()}`;
};
devicesView = function() {
 let html=baseDevicesView();
 if (sampleMode() && !(state.device.metrics||[]).length) {
  html=html.replace('<div class="health-grid">',`<section class="sample-health"><div class="sectionhead"><h2>状态卡片预览</h2><span class="badge neutral">示例数据</span></div>
   <div class="state-cards">${state.experience.metrics.map(metric=>`<div class="state-tile"><span>${esc(metric.label)}</span>
    <b>${esc(metric.value)}<small>${esc(metric.unit)}</small></b><small>示例 · 非设备实测</small></div>`).join('')}</div>
   <p class="micro">导入自己的记录后显示真实来源与采集时间。</p></section><div class="health-grid">`);
 }
 return html;
};
settingsView = function() {
 return baseSettingsView()+`<div class="card"><button class="settingsrow" data-exp="intro">
  <span class="rowmain"><strong>关于体验版</strong><small>示例场景、照片来源与数据说明</small></span>${icon('chev')}</button></div>`;
};

const originalRender = render;
render = function() {
 document.body.dataset.screen=route().page;
 originalRender();
};

function intro() {
 showSheet(`<h2>体验两次调整</h2>
  <p class="textbody">先选「只有 30 分钟」，把器械设为只有弹力带，比较候选后确认安排。练后可试填「部分完成、20 分钟、偏累」。下次调整先把当天状态留空，看看 Pivot 会问什么。</p>
  <p class="textbody">示例状态卡不代表穿戴设备实测。各浏览器独立记录，设备页支持文件导入。</p>
  <p class="micro">力量参考图来自 free-exercise-db（Unlicense）。球场照片：<a href="https://unsplash.com/photos/k75KSGiZWAE" target="_blank" rel="noreferrer">Nikita Pishchugin / Unsplash</a>。</p>
  <button class="btn primary wide" data-action="close-sheet">开始体验</button>`);
}

document.addEventListener('click',event=>{
 const trigger = event.target.closest('button[data-exp]');
 if (!trigger || busy) return;
 const {exp:action,value} = trigger.dataset;
 if (action === 'quick') quickSheet(value);
 if (action === 'reschedule' && currentTask()?.status==='needs_info') rescheduleSheet(currentTask());
 if (action === 'feedback') feedbackSheet(value);
 if (action === 'intro') intro();
 if (action === 'plan-detail' || action === 'day' && value === state.plan.date) {
  showSheet(`<h2>${esc(state.plan.title)}</h2><p class="micro">${schedule(state.plan)}</p>
   ${state.plan.actions?.length?catalogActionList(state.plan.actions):`<p class="textbody">${esc(state.plan.content||'尚未填写具体训练内容')}</p>`}<p class="micro">${esc(state.plan.source)}</p>
   <div class="actions"><button class="btn primary" ${state.plan.actions?.length&&state.trainingCatalog?'data-catalog="record-plan"':'data-nav="training" data-exp="close-nav"'}>记录训练 ${icon('arrow')}</button>
   <button class="btn soft" data-action="edit-plan">编辑计划</button></div>`);
 } else if (action === 'day' && value === state.goalContext?.eventDate) {
  showSheet(`<h2>${esc(state.goalContext.eventName)}</h2><p class="textbody">${esc(value)}</p>
   <button class="btn primary wide" data-action="edit-profile">编辑活动安排</button>`);
 } else if (action === 'day') {
  selectedDate=value; calendarMonth=value.slice(0,7); go('history');
 }
 if (action === 'close-nav') closeSheet();
 if (action === 'metric') {
  const real = state.permissions.device && state.device.metrics?.length;
  const metric = (real?state.device.metrics:state.experience.metrics)[Number(value)];
  showSheet(`<h2>${esc(metric.label)}</h2><div class="metric-detail">${esc(metric.value)} <small>${esc(metric.unit)}</small></div>
   <p>${real?esc(metric.source):'示例数据 · 没有连接真实设备'}</p>
   <p class="micro">${real?esc(stamp(metric.at)):'示例数值仅供了解界面，不参与调整。'}</p>
   <button class="btn primary wide" data-exp="device-nav">${real?'管理记录':'导入我的数据'}</button>`);
 }
 if (action === 'device-nav') { closeSheet(); go('devices'); }
});

document.addEventListener('change',event=>{
 const target = event.target;
 if (target.form?.id === 'quick-form' && target.name === 'equipment') {
  const field = $('#quick-other-equipment');
  field.hidden = target.value !== 'custom';
  const input = field.querySelector('input');
  input.disabled = field.hidden;
  input.required = !field.hidden;
 }
 if (target.form?.id === 'quick-feedback' && target.name === 'completion') {
  target.form.elements.minutes.readOnly = target.value === 'not_done';
 }
 if (target.name === 'optionId' && route().page === 'task') {
  const hadFocus = document.activeElement === target;
  render();
  if (hadFocus) document.querySelector('#confirm-form input[name="optionId"]:checked')?.focus({preventScroll:true});
 }
});

document.addEventListener('submit',async event=>{
 const form = event.target;
 if (!['quick-form','quick-feedback','reschedule-training-form'].includes(form.id)) return;
 event.preventDefault();
 if (busy) return;
 const data = new FormData(form);
 if (form.id === 'reschedule-training-form') {
  const date = data.get('date'), time = data.get('time');
  await mutation('answer',{id:form.dataset.task,text:`改到 ${date} ${time}`,context:{scenario:'ball',date,time}},event.submitter,()=>{
   answerInput=''; answerTaskId=''; persistDraftInput(); closeSheet();
  });
  return;
 }
 if (form.id === 'quick-form') {
  const scenario = form.dataset.scenario;
  const equipment = (data.get('equipment') === 'custom' ? data.get('otherEquipment') : data.get('equipment'))?.trim();
  const context = {
   scenario,
   condition:data.get('condition'),
   ...(scenario==='tired' && {sleepChanged:data.has('sleepChanged')}),
   ...(data.get('minutes') && {minutes:Number(data.get('minutes'))}),
   ...(equipment && {equipment}),
   ...(data.get('date') && {date:data.get('date')}),
   ...(data.get('time') && {time:data.get('time')}),
   ...(data.get('restriction')?.trim() && {restriction:data.get('restriction').trim()}),
  };
  const summary = scenario === 'short' ? `今天只有 ${context.minutes} 分钟` : quickScenarios[scenario].title;
  const input = [summary, context.equipment && `器械：${context.equipment}`, context.restriction && `限制：${context.restriction}`].filter(Boolean).join('，');
  await mutation('tasks',{input,entry:'quick',context},event.submitter,()=>{
   taskInput=''; closeSheet(); go('task/'+state.activeTask.id);
  });
  return;
 }
 const completion = data.get('completion');
 const example = sampleMode();
 const payload = {
  idempotencyKey:feedbackKey, taskId:form.dataset.task, completion,
  minutes:completion==='not_done'?0:Number(data.get('minutes')), feeling:data.get('feeling'),
  discomfort:data.has('discomfort'), note:(example?'[示例体验反馈] ':'')+String(data.get('note')||''),
  performedAt:todayISO(), exercise:'general', exerciseName:example?'示例训练反馈':'力量训练',
  sets:1, reps:0, weight:0,
 };
 await mutation('sessions',payload,event.submitter,()=>{
  closeSheet(); notify(example?'示例反馈已保存':'训练反馈已保存'); go('today');
 });
});

install = async function() {
 if (matchMedia('(display-mode: standalone)').matches || navigator.standalone === true) {
  showSheet('<h2>已从主屏幕打开</h2><p class="textbody">现在可以从手机桌面的换场图标进入。</p><button class="btn primary wide" data-action="close-sheet">知道了</button>');
  return;
 }
 if (deferredInstall) { await deferredInstall.prompt(); deferredInstall=null; return; }
 if (['localhost','127.0.0.1','[::1]'].includes(location.hostname)) {
  showSheet('<h2>在手机上添加换场</h2><p class="textbody">在手机的 Safari 中打开换场的 HTTPS 体验链接，然后点「分享」→「添加到主屏幕」。</p><button class="btn primary wide" data-action="close-sheet">知道了</button>');
  return;
 }
 showSheet(`<h2>把换场放到手机桌面</h2><p class="textbody">iPhone：在 Safari 打开此链接，轻点「分享」→「添加到主屏幕」。</p>
  <p class="textbody">Android：在 Chrome 菜单选择「安装应用」或「添加到主屏幕」。</p>
  <button class="btn primary wide" data-action="close-sheet">知道了</button>`);
};
if (state) render();
