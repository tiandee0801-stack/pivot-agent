/* Pivot mobile product edition. Training layout adapted from Good-GYM (MIT). */
var selectedExercise='squat', cameraStream=null, cameraFacing='environment', recorder=null;
function studioRoute(){return state?.trainingCatalog?'training/video':'training';}
let cameraRequest=0,cameraPending=false,cameraHelp='',cameraTicker=null,recordingTimer=null;
const exerciseLibrary=[
 {id:'squat',name:'深蹲',en:'SQUAT',group:'下肢',hint:'侧面拍摄 · 髋、膝、踝完整入镜',points:'髋 → 膝 → 踝'},
 {id:'pushup',name:'俯卧撑',en:'PUSH-UP',group:'胸部',hint:'侧面拍摄 · 肩、肘、腕清楚可见',points:'肩 → 肘 → 腕'},
 {id:'bicep_curl',name:'哑铃弯举',en:'BICEP CURL',group:'手臂',hint:'侧前方拍摄 · 完整拍下伸展和回落',points:'肩 → 肘 → 腕'},
 {id:'lateral_raise',name:'侧平举',en:'LATERAL RAISE',group:'肩部',hint:'正面拍摄 · 双臂抬起时完整入镜',points:'髋 → 肩 → 肘'},
 {id:'overhead_press',name:'肩上推举',en:'OVERHEAD PRESS',group:'肩部',hint:'侧前方拍摄 · 髋、肩、肘清晰可见，举过头顶时手臂仍在画面内',points:'髋 → 肩 → 肘'}
];
const manualSports=[{id:'basketball',name:'篮球'},{id:'badminton',name:'羽毛球'},{id:'running',name:'跑步'},{id:'general',name:'自主训练'}];
const exerciseName=id=>[...exerciseLibrary,...manualSports].find(x=>x.id===id)?.name||'训练';
const currentExercise=()=>exerciseLibrary.find(x=>x.id===selectedExercise)||exerciseLibrary[0];
const originalRecordForm=recordForm;
const originalAttachVideo=attachVideo;
const oldSessionRow=sessionRow;
const originalSessionView=sessionView;
recordForm = function(options={}){
 originalRecordForm(options);const f=$('#session-form'),s=options.session||{};if(!f)return;
 if(options.quickBasketball){
  f.insertAdjacentHTML('afterbegin','<input type="hidden" name="exercise" value="basketball">');
  return;
 }
 const ex=s.exercise||s.observation?.exercise||options.result?.exercise||(options.videoJobId?selectedExercise:'general');
 f.insertAdjacentHTML('afterbegin',`<label class="field">训练动作 / 运动<select name="exercise">${[...exerciseLibrary,...manualSports].map(e=>`<option value="${e.id}" ${e.id===ex?'selected':''}>${e.name}</option>`).join('')}</select></label><div class="formgrid three"><label class="field">组数<input name="sets" type="number" min="1" max="20" value="${s.sets||1}" required></label><label class="field">总次数<input name="reps" type="number" min="0" max="1000" value="${s.reps??options.result?.count??0}" required></label><label class="field">重量 kg<input name="weight" type="number" min="0" max="500" step="0.5" value="${s.weight||0}" required></label></div>`);
}
function sessionRow(s){return `<button class="row" data-nav="session/${esc(s.id)}"><span class="exercise-icon small">${icon('training')}</span><span class="rowmain"><strong>${esc(s.exerciseName||s.observation?.exerciseName||'自主训练')}</strong><small>${esc(s.performedAt)} · ${esc(s.minutes)} 分钟 · ${esc(completionNames[s.completion])}</small></span><span class="rowend">${s.observation?.confirmedCount!=null?s.observation.confirmedCount+' 次':s.reps?s.reps+' 次':icon('chev')}</span></button>`;}
sessionView = function(){const s=currentSession();let html=originalSessionView();if(s&&s.exercise!=='basketball')html=html.replace('<p class="textbody">',`<p class="set-summary">${esc(s.sets||1)} 组 · ${esc(s.reps||s.observation?.confirmedCount||0)} 次 · ${esc(s.weight||0)} kg</p><p class="textbody">`);return html;}
function todayView(){
 const p=state.plan,ongoing=state.activeTask&&['needs_info','draft'].includes(state.activeTask.status),wk=weekStats(),goal=state.weeklyGoal||3;
 return `${head('把训练，接回生活。',dateLabel(todayISO()))}<section class="plan-hero"><div class="hero-kicker"><span class="status-dot"></span>${state.planIsExample?'设置你的第一份计划':'你的训练安排'}<button class="text-icon" data-action="edit-plan" aria-label="编辑训练计划">${icon('edit')}</button></div><h2>${esc(p.title)}</h2><div class="hero-time"><b>${p.minutes}</b><span>MIN<br><small>${esc(p.time)} 开始</small></span></div><div class="hero-bottom"><span>${esc(dateLabel(p.date))}</span><button data-nav="training">开始训练 ${icon('arrow')}</button></div>${p.purpose?`<p class="goal-context-line">${esc(p.purpose)}</p>`:''}${p.content?`<div class="plan-content-preview">${esc(p.content)}</div>`:''}</section>
 <section class="card agent-card"><div class="agenthead">${icon('agent')}PIVOT AGENT <span>持续为你安排</span></div>${ongoing?`<h2>接着完成这次调整</h2><p class="textbody">${esc(state.activeTask.input)}</p><button class="btn primary wide" style="margin-top:18px" data-nav="task/${state.activeTask.id}">继续调整 ${icon('arrow')}</button><button class="linkbtn" data-v2="fresh-task">重新开始一次调整</button>`:`<form id="task-form"><h2>今天的安排，有变化？</h2><p class="subtle introline">时间不够、临时约球，或者想轻松一点。</p><textarea id="agent-input" name="input" required maxlength="500" placeholder="告诉我变化，例如今天只剩 30 分钟…">${esc(taskInput)}</textarea><div class="chips"><button type="button" class="chip" data-prompt="今天只有30分钟，没有不适，帮我调整原计划">只剩 30 分钟</button><button type="button" class="chip" data-prompt="昨天临时打了篮球，今天没有不适，帮我调整原计划">昨晚打了球</button><button type="button" class="chip" data-prompt="未来两周工作忙，我想先保持运动习惯">最近比较忙</button></div>${errorBox()}<button class="btn primary wide" type="submit">帮我调整 ${icon('arrow')}</button></form>`}</section>
 ${pendingConfirmation?`<div class="notice warn">上一次保存需要核对。${button('check-operation','查看结果','soft')}</div>`:''}
 ${(state.history||[]).some(t=>t.receipt?.planSaved&&!(state.sessions||[]).some(s=>s.taskId===t.id))?`<section class="card"><h2>安排之后，接着跟进</h2><p class="micro" style="margin:9px 0">记录是否完成和训练感受，下一次安排会参考你的实际反馈。</p>${(state.history||[]).filter(t=>t.receipt?.planSaved&&!(state.sessions||[]).some(s=>s.taskId===t.id)).slice(0,2).map(t=>`<button class="row" data-nav="task/${t.id}"><span class="rowmain"><strong>${esc(t.original?.title||'训练安排')}</strong><small>已保存安排 · 等待实际反馈</small></span>${icon('chev')}</button>`).join('')}</section>`:''}<div class="dashboard-grid"><button class="metric-card" data-nav="goals"><span>本周训练</span><b>${wk.done.size}<small> / ${goal} 天</small></b><div class="mini-track"><i style="width:${Math.min(100,wk.done.size/goal*100)}%"></i></div></button><button class="metric-card" data-action="add-record"><span>记录球类或力量训练</span><b class="plus">＋</b><small>手动添加记录</small></button></div>
 <button class="home-device" data-nav="devices">${icon('watch')}<span><strong>${esc(state.device.label)}</strong>${state.device.metrics?.length?'查看来源与时间，管理数据使用':'导入 Apple 健康或 Garmin 记录'}</span>${icon('chev')}</button>${section('训练动作',`<button class="linkbtn" data-v2="exercise-picker">查看全部 ${icon('chev')}</button>`)}<div class="exercise-strip">${exerciseLibrary.map((e,i)=>`<button class="exercise-tile" data-exercise="${e.id}"><span class="exercise-icon">${exerciseGlyph(e.id)}</span><strong>${e.name}</strong><small>${e.group} · 视频计数</small></button>`).join('')}</div>
 ${section('最近的训练',`<button class="linkbtn" data-nav="history">全部记录</button>`)}<div class="card list">${(state.sessions||[]).slice(0,3).map(sessionRow).join('')||`<div class="empty-min"><h3>每一次训练，都值得记录</h3><p>拍摄训练或手动记录，反馈会用于下一次安排。</p><button class="linkbtn" data-nav="training">去记录第一组 ${icon('arrow')}</button></div>`}</div>
 ${section('可用的替代方案',`<button class="linkbtn" data-action="edit-alternatives">管理</button>`)}<div class="card list">${state.alternatives.map(a=>`<button class="row" data-action="edit-alternatives"><span class="rowicon">${icon('clock')}</span><span class="rowmain"><strong>${esc(a.title)}</strong><small>${esc(a.source)}</small></span><span class="rowend">${a.minutes} 分钟</span></button>`).join('')}</div>`;
}
function exerciseGlyph(id){const shapes={squat:'<circle cx="12" cy="4" r="2"/><path d="m10 8-3 6 6 1-3 6m0-13 5 5 5 0m-8 2 6 2-1 5"/>',pushup:'<circle cx="19" cy="5" r="2"/><path d="m16 8-6 4-6 1-2 3m14-8 2 7-4 5m-4-8 5 4"/>',bicep_curl:'<circle cx="12" cy="4" r="2"/><path d="M11 8v7m0 0-3 7m3-7 4 7M10 9l-5 5-2-5m11 0 4 5 3-5"/>',lateral_raise:'<circle cx="12" cy="4" r="2"/><path d="M12 8v7m0-6L2 7m10 2 10-2M12 15l-4 7m4-7 4 7"/>',overhead_press:'<circle cx="12" cy="6" r="2"/><path d="M12 10v6m0 0-4 6m4-6 4 6M9 11 4 7V2m11 9 5-4V2"/>'};return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">${shapes[id]||shapes.squat}</svg>`;}
function chooseExercise(){showSheet(`<h2>选择训练动作</h2><p class="subtle">五种动作 · 各自独立的关键点和计数规则</p><div class="picker-list">${exerciseLibrary.map(e=>`<button class="row" data-exercise="${e.id}"><span class="exercise-icon small">${exerciseGlyph(e.id)}</span><span class="rowmain"><strong>${e.name}</strong><small>${e.hint}</small></span><span class="rowend">${selectedExercise===e.id?'✓':icon('chev')}</span></button>`).join('')}</div><p class="micro">篮球、羽毛球和跑步可在「手动记录」中记录。</p>`);}
function trainingView(){
 const e=currentExercise(),v=videoState,r=v.result,job=v.job,working=v.uploading||['queued','running'].includes(job?.status),media=validMedia(r?.sourceUrl)||v.blobUrl,hasCamera=!!cameraStream,recording=recorder?.state==='recording';
 return `<div class="studio-toolbar"><button class="exercise-select" data-v2="exercise-picker" ${working||recording?'disabled':''}>${e.name}<span>⌄</span></button><div class="studio-actions"><button class="round-tool" data-action="pick-video" aria-label="上传视频" ${working||recording?'disabled':''}>${icon('upload')}</button><button class="round-tool red" data-v2="open-camera" aria-label="打开摄像头" ${working||hasCamera||cameraPending?'disabled':''}>${icon('record')}</button><button class="round-tool" data-v2="flip-camera" aria-label="切换摄像头" ${working||recording||cameraPending?'disabled':''}>${icon('video')}</button></div></div>
 <div class="studio-label"><button class="linkbtn" data-action="capture-guide">拍摄指南 ${icon('chev')}</button></div>
 <input id="video-file" type="file" accept="video/*" hidden><input id="video-camera" type="file" accept="video/*" capture="${cameraFacing}" hidden>
 <div class="video-stage ${hasCamera?'camera-open':''}">${hasCamera?`<video id="camera-preview" autoplay muted playsinline aria-label="相机预览"></video><span class="live-label" id="record-timer">${recording?'正在录制':'相机已就绪'}</span><div class="camera-instruction">${e.hint}</div>`:media?`<video id="training-video" src="${esc(media)}" controls playsinline preload="metadata" aria-label="训练视频"></video><canvas id="pose-canvas" aria-hidden="true"></canvas>${r?`<div class="rep-overlay"><b id="rep-current">${r.quality==='usable'?'0':'—'}</b><span>动作次数</span></div><div class="video-tools"><button data-action="toggle-overlay" aria-pressed="${v.overlay}" aria-label="骨架叠加">${v.overlay?'隐藏骨架':'显示骨架'}</button></div>`:''}`:`<div class="studio-empty"><div class="framing"><span></span><span></span><span></span><span></span></div><div class="camera-symbol">${icon('video')}</div><h2>${job?.mediaDeleted?'视频已不可回放':'准备好，就开始。'}</h2><p>${job?.mediaDeleted?'视频已删除或超过保留期限，分析记录仍可查看。':e.hint}</p><button class="btn primary" data-v2="open-camera" ${working||cameraPending?'disabled':''}>打开摄像头</button><button class="linkbtn" data-action="pick-video" ${working?'disabled':''}>从相册上传视频</button></div>`}${working?`<div class="videostatus">${v.uploading?'正在上传视频':job?.status==='queued'?'已排队等待分析':'正在提取动作关键点'}<span id="progress-label"> ${Math.round(v.progress)}%</span><div class="progress"><span id="progress-bar" style="width:${v.progress}%"></span></div></div>`:''}</div>
 ${cameraPending?`<div class="notice"><p role="status">等待相机权限。可在浏览器的提示中选择是否允许。</p><button class="btn soft" data-v2="close-camera">取消等待</button></div>`:''}
 ${cameraHelp?`<div class="notice warn"><p role="status">${esc(cameraHelp)}</p><div class="actions">${button('record-video','使用系统拍摄','soft')}${button('pick-video','从相册上传视频','soft')}</div></div>`:''}
 ${hasCamera?`<div class="record-controls"><button class="linkbtn" data-v2="close-camera">关闭相机</button><button class="shutter ${recorder?.state==='recording'?'recording':''}" data-v2="camera-record" aria-label="${recorder?.state==='recording'?'结束录制':'开始录制'}"><span></span></button><small>最长 45 秒</small></div><p class="micro center">录制结束后分析动作，原视频可回放核对。</p>`:''}
 ${v.file?`<p class="uploadname">${esc(v.file.name)} · ${(v.file.size/1048576).toFixed(1)} MB</p>`:''}
 ${v.error?`<div class="notice warn" role="alert">${esc(v.error)}${job?.jobId?button('retry-job','检查处理状态','soft'):''}</div>`:''}
 ${!r&&!working&&!hasCamera?`<form id="upload-form" class="analysis-controls"><div class="segmented"><label><input type="radio" name="side" value="left" ${v.side==='left'?'checked':''}><span>身体左侧</span></label><label><input type="radio" name="side" value="right" ${v.side==='right'?'checked':''}><span>身体右侧</span></label></div><label class="check video-consent"><input type="checkbox" name="consent" required ${v.consent?'checked':''}><span>同意上传至 Pivot 分析服务并保留回放最多 7 天，可随时删除。</span></label><button class="btn primary wide" ${v.file?'':'disabled'}>分析${e.name}动作 ${icon('arrow')}</button><p class="micro center" style="margin:12px 0">0.3–45 秒 · 60 MB 内 · 视频仅在此应用的分析服务处理</p></form>`:''}
 ${r?`<section class="card result-card"><div class="buttonrow"><h2>${esc(r.exerciseName||e.name)} · 分析结果</h2><span class="badge ${r.quality==='usable'?'':'warn'}">${r.quality==='usable'?'分析完成':'请人工核对'}</span></div><div class="result-grid"><div><b>${r.count==null?'—':r.count}<small> 次</small></b><span>完整动作周期</span></div><div><b>${r.cycleDurationSeconds==null?'—':r.cycleDurationSeconds}<small> 秒</small></b><span>相邻周期节奏</span></div></div>${r.quality!=='usable'?'<p class="textbody">画面信息不足，未获得可靠次数。</p>':''}<p class="textbody">${esc(r.summary)}</p><div class="quality-meter"><i style="width:${Math.round(r.validRatio*100)}%"></i></div><p class="micro">可观察画面 ${Math.round(r.validRatio*100)}%${media?' · 可回放校正':''}</p><div class="actions">${button('record-video-result','核对并保存训练')}${button('new-video','下一组','soft')}</div><details><summary>分析依据与范围</summary><p>${esc(e.points)} · ${esc(r.ruleVersion)}</p><p class="micro">只统计二维动作周期，不能代替动作标准或训练强度判断。</p></details></section>`:''}
 <div class="studio-footer"><button class="card quick-record" data-action="add-record"><span class="rowicon">${icon('edit')}</span><span class="rowmain"><strong>手动记录训练</strong><small>球类、跑步、组数与重量</small></span>${icon('chev')}</button></div>
 ${section('最近的视频',`<button class="linkbtn" data-action="refresh-videos">刷新</button>`)}<div class="card list">${(state.videoJobs||[]).slice(0,8).map(j=>`<div class="row"><button class="settingsrow" data-open-job="${j.jobId}" style="padding:0"><span class="exercise-icon small">${exerciseGlyph(j.exercise)}</span><span class="rowmain"><strong>${esc(j.exerciseName||'弯举')} · ${j.status==='done'?'已分析':j.status==='error'?'需重试':'处理中'}</strong><small>${esc(stamp(j.createdAt))}</small></span>${icon('chev')}</button><button class="iconbtn" data-delete-job="${j.jobId}" aria-label="删除这段训练视频">${icon('trash')}</button></div>`).join('')||'<div class="empty-min"><p>上传的训练视频会保存在这里。</p></div>'}</div>`;
}
attachVideo = function(){originalAttachVideo();if(cameraStream&&$('#camera-preview')){$('#camera-preview').srcObject=cameraStream;$('#camera-preview').style.transform=state?.trainingPreferences?.mirror?'scaleX(-1)':'';}const video=$('#training-video');if(video){let last=-1;video.addEventListener('timeupdate',()=>{const frames=videoState.result?.frames||[];const frame=[...frames].reverse().find(f=>f.t<=video.currentTime);if(frame?.count>last){if(last>=0&&frame.count>0){if(state.trainingPreferences?.sound)beep();if(state.trainingPreferences?.speak&&'speechSynthesis'in window){const u=new SpeechSynthesisUtterance(String(frame.count));u.lang='zh-CN';speechSynthesis.speak(u);}}last=frame?.count||0;}});}}
function beep(){try{const C=window.AudioContext||window.webkitAudioContext,c=new C(),o=c.createOscillator(),g=c.createGain();o.frequency.value=660;g.gain.value=.07;o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+.10);o.onended=()=>c.close();}catch{}}
async function openCamera(){
 if(route().page!=='training'||cameraPending||cameraStream)return;
 if(!navigator.mediaDevices?.getUserMedia){
  showCameraHelp('当前浏览器无法打开相机预览，可使用系统拍摄或从相册上传。');
  return;
 }
 const request=++cameraRequest;
 cameraPending=true;cameraHelp='';render();
 try{
  const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:cameraFacing},width:{ideal:720},height:{ideal:1280}},audio:false});
  if(request!==cameraRequest||route().page!=='training'||document.hidden){
   stream.getTracks().forEach(track=>track.stop());
   if(request===cameraRequest){cameraPending=false;if(route().page==='training')render();}
   return;
  }
  cameraStream=stream;
  for(const track of stream.getTracks()){
   track.addEventListener('ended',()=>{
    if(cameraStream===stream){stopCamera();showCameraHelp('相机已断开，可重新打开或从相册上传。');}
   },{once:true});
  }
  cameraPending=false;render();
 }catch(error){
  if(request!==cameraRequest||route().page!=='training')return;
  cameraPending=false;
  showCameraHelp(error.name==='NotAllowedError'?'相机权限未开启。可在浏览器中检查权限，或从相册上传。':'暂时无法打开相机，可使用系统拍摄或从相册上传。');
 }
}
function showCameraHelp(message){cameraHelp=message;if(route().page==='training')render();}
function stopCamera(){
 cameraRequest++;cameraPending=false;cameraHelp='';
 const stoppedRecorder=recorder;recorder=null;
 if(stoppedRecorder&&stoppedRecorder.state!=='inactive')stoppedRecorder.stop();
 clearTimeout(recordingTimer);clearInterval(cameraTicker);
 const stoppedStream=cameraStream;cameraStream=null;
 stoppedStream?.getTracks().forEach(track=>track.stop());
}
function recordCamera(){
 if(!cameraStream)return openCamera();
 if(recorder){if(recorder.state==='recording')recorder.stop();return;}
 if(!window.MediaRecorder){stopCamera();showCameraHelp('当前浏览器不支持网页内录制，可使用系统拍摄或从相册上传。');return;}
 const formats=['video/mp4','video/webm;codecs=vp8','video/webm'];
 const mime=formats.find(format=>MediaRecorder.isTypeSupported?.(format));
 try{
  const activeRecorder=new MediaRecorder(cameraStream,mime?{mimeType:mime}:undefined),chunks=[];
  recorder=activeRecorder;
  activeRecorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
  activeRecorder.onerror=()=>{
   if(recorder!==activeRecorder)return;
   stopCamera();showCameraHelp('录制中断，可重新拍摄或从相册上传。');
  };
  activeRecorder.onstop=()=>{
   if(recorder!==activeRecorder)return;
   stopCamera();
   if(route().page!=='training')return;
   if(!chunks.length){showCameraHelp('没有录到视频，可重新拍摄或从相册上传。');return;}
   const type=activeRecorder.mimeType||chunks[0].type;
   const extension=type.includes('mp4')?'mp4':'webm';
   const file=new File(chunks,`Pivot-${selectedExercise}-${Date.now()}.${extension}`,{type});
   if(!setVideoFile(file))render();
  };
  activeRecorder.start();const started=Date.now();render();
  cameraTicker=setInterval(()=>{const timer=$('#record-timer');if(timer)timer.textContent=String(Math.floor((Date.now()-started)/1000)).padStart(2,'0')+' / 45 秒';},250);
  recordingTimer=setTimeout(()=>{if(activeRecorder.state==='recording')activeRecorder.stop();},45000);
 }catch{
  stopCamera();showCameraHelp('录制未能开始，可使用系统拍摄或从相册上传。');
 }
}
function captureGuide(){const e=currentExercise();showSheet(`<h2>${e.name}拍摄指南</h2><div class="guide-hero">${exerciseGlyph(e.id)}<strong>${e.points}</strong></div><ol><li>${e.hint}，固定手机，避免镜面反射。</li><li>画面中只保留一人，光线充足，不遮挡关键关节。</li><li>完整拍下动作起始、发力和回落，最长 45 秒。</li><li>选择身体本人的左侧或右侧。分析后播放视频核对，有误可修改次数。</li></ol><button class="btn primary wide" data-v2="guide-camera">知道了，去拍摄</button>`);}
function goalsView(){const {dates,done}=weekStats(),goal=state.weeklyGoal||3,goals=state.exerciseGoals||{};return `${head('目标','YOUR GOALS')}<section class="card limecard goal-hero"><div class="goal-overview"><div><span class="rowicon">${icon('goals')}</span><h2>每周目标</h2><p class="subtle">本周已训练 ${done.size} / ${goal} 天</p></div><div class="ring" style="--progress:${Math.min(100,done.size/goal*100)}%"><div class="ringinner"><b>${done.size}</b><small>/ ${goal} 天</small></div></div></div><div class="weekdots">${dates.map((d,i)=>`<span><b class="${done.has(d)?'done':''}"></b>${'一二三四五六日'[i]}</span>`).join('')}</div><form id="weekly-form"><div class="goalchoices">${Array.from({length:7},(_,i)=>`<label><input type="radio" name="goal" value="${i+1}" ${goal===i+1?'checked':''}><span>${i+1}天</span></label>`).join('')}</div>${errorBox()}<button class="linkbtn" style="width:100%;justify-content:center;margin-top:14px">保存每周目标</button></form></section>
 ${section('每日动作目标')}<form id="exercise-goals-form">${exerciseLibrary.map(e=>{const records=state.sessions.filter(s=>s.performedAt===todayISO()&&(s.exercise||s.observation?.exercise)===e.id);const actual=records.reduce((n,s)=>n+(s.observation?.confirmedCount??s.reps??0),0);return `<div class="card daily-goal"><span class="exercise-icon">${exerciseGlyph(e.id)}</span><div class="rowmain"><strong>${e.name}</strong><small>今天已记录 ${actual} 次</small></div><label class="goal-input"><input type="number" name="${e.id}" value="${goals[e.id]??30}" min="0" max="1000" aria-label="${e.name}每日目标"><small>次</small></label></div>`;}).join('')}${errorBox()}<button class="btn primary wide" style="margin-bottom:18px">保存动作目标</button></form><p class="micro">目标由你自行设置，用于记录进度。填 0 可关闭该动作目标。</p>${section('阶段目标与运动偏好',`<button class="linkbtn" data-action="edit-profile">编辑</button>`)}<div class="card"><h3>${esc(state.profile.goal)}</h3><p class="subtle" style="margin-top:10px">${esc(state.profile.sport)} · ${esc(state.profile.preferredTime)}</p>${state.goalContext?.endDate?`<p class="goal-context-line">阶段目标截至 ${esc(state.goalContext.endDate)}${state.goalContext.endDate<todayISO()?' · 已到期，请重新确认':''}</p>`:''}${state.goalContext?.eventName?`<p class="goal-context-line">近期重要活动：${esc(state.goalContext.eventName)} · ${esc(state.goalContext.eventDate)}</p>`:''}</div>`;}
function settingsView(){const pref=state.trainingPreferences||{};const setting=(key,title,sub)=>`<label class="settingsrow"><span class="rowmain"><strong>${title}</strong><small>${sub}</small></span><input class="toggle" type="checkbox" name="${key}" ${pref[key]?'checked':''}></label>`;return `${head('设置','MAKE IT YOURS')}<section class="card app-identity"><div class="app-icon">P<span>↗</span></div><div><h2>PIVOT<span> 换场</span></h2><p>你的运动，接着往下走。</p></div><div class="identity-tags"><span>训练计划</span><span>穿戴记录</span><span>五动作观察</span></div></section>
 <section class="card list"><button class="settingsrow" data-nav="goals"><span class="rowicon">${icon('goals')}</span><span class="rowmain"><strong>运动目标</strong><small>每周训练与动作进度</small></span>${icon('chev')}</button><button class="settingsrow" data-action="edit-profile"><span class="rowicon">${icon('settings')}</span><span class="rowmain"><strong>个人档案</strong><small>阶段目标、偏好和训练限制</small></span>${icon('chev')}</button><button class="settingsrow" data-action="edit-plan"><span class="rowicon">${icon('today')}</span><span class="rowmain"><strong>我的计划</strong><small>时间、内容、训练目的和器械</small></span>${icon('chev')}</button><button class="settingsrow" data-action="edit-alternatives"><span class="rowicon">${icon('training')}</span><span class="rowmain"><strong>替代方案</strong><small>维护你认可的短时训练安排</small></span>${icon('chev')}</button></section>
 <form id="training-prefs-form"><section class="card"><h2>声音与画面</h2>${setting('sound','计数提示音','回放每完成一个动作时提示')}${setting('speak','语音报数','回放时读出已完成次数')}${setting('skeleton','默认显示骨骼','视频回放时叠加真实关键点')}${setting('mirror','相机镜像','左右翻转相机预览，不改变原视频')}${errorBox()}<button class="btn soft wide">保存训练设置</button></section></form>
 <section class="card list"><button class="settingsrow" data-action="install"><span class="rowicon">${icon('export')}</span><span class="rowmain"><strong>添加到主屏幕</strong><small>从手机桌面打开</small></span>${icon('chev')}</button><button class="settingsrow" data-action="export"><span class="rowicon">${icon('note')}</span><span class="rowmain"><strong>导出训练数据</strong><small>保存你的计划与历史记录</small></span>${icon('chev')}</button><button class="settingsrow" data-action="privacy"><span class="rowicon">${icon('shield')}</span><span class="rowmain"><strong>隐私与数据</strong><small>独立空间 · 视频保留 7 天 · 可删除</small></span>${icon('chev')}</button><button class="settingsrow" data-v2="about"><span class="rowmain"><strong>关于 Pivot</strong><small>开源能力与版本信息</small></span>${icon('chev')}</button></section>`;}
document.addEventListener('click',async event=>{const el=event.target.closest('button');if(!el)return;if(el.dataset.exercise){stopCamera();selectedExercise=el.dataset.exercise;clearVideo();videoState.overlay=state.trainingPreferences?.skeleton!==false;closeSheet();go(studioRoute());render();return;}const a=el.dataset.v2;if(!a)return;
 if(a==='exercise-picker')chooseExercise();
 if(a==='open-camera')openCamera();
 if(a==='flip-camera'){
  if(cameraPending||recorder)return;
  cameraFacing=cameraFacing==='environment'?'user':'environment';
  if(cameraStream){stopCamera();openCamera();}
  else{const nativeCapture=$('#video-camera');if(nativeCapture)nativeCapture.setAttribute('capture',cameraFacing);notify('下次打开将使用'+(cameraFacing==='user'?'前置':'后置')+'摄像头');}
 }
 if(a==='close-camera'){stopCamera();render();}
 if(a==='camera-record')recordCamera();
 if(a==='guide-camera'){closeSheet();openCamera();}
 if(a==='fresh-task'){const t=state.activeTask;try{state=await api('cancel',{id:t.id});taskInput='';render();}catch(e){notify(e.message);}}
 if(a==='about'){
  const version=typeof health?.demoVersion==='string'?` · V${esc(health.demoVersion)}`:'';
  showSheet(`<h2>Pivot 换场${version}</h2><p>围绕运动计划调整、实际训练和持续反馈的 Personal Agent。</p><p style="margin-top:15px">训练页面与多动作计数规则参考 Good-GYM（MIT），人体关键点由 RTMPose / YOLOX 提取。</p><p class="micro" style="margin-top:15px">五种动作采用独立的观察规则。次数与画面质量可人工核对，不据此自动判断动作标准或康复结论。</p>`);
 }
});
document.addEventListener('submit',async event=>{const f=event.target;if(!['exercise-goals-form','training-prefs-form'].includes(f.id))return;event.preventDefault();const data=new FormData(f),b=event.submitter;
 if(f.id==='exercise-goals-form'){const values=Object.fromEntries(exerciseLibrary.map(e=>[e.id,Number(data.get(e.id))]));await mutation('settings',{exerciseGoals:values},b,()=>notify('每日动作目标已保存'));}
 else{const values=Object.fromEntries(['sound','speak','skeleton','mirror'].map(k=>[k,data.has(k)]));await mutation('settings',{trainingPreferences:values},b,()=>{videoState.overlay=values.skeleton;notify('声音与画面设置已保存');});}
});
document.addEventListener('change',event=>{
 const input=event.target;
 if((input.id==='video-file'||input.id==='video-camera')&&input.files?.length&&(cameraStream||cameraPending||cameraHelp)){
  stopCamera();render();
 }
},true);
window.addEventListener('hashchange',()=>{if(location.hash!=='#'+studioRoute())stopCamera();});
window.addEventListener('pagehide',stopCamera);
window.addEventListener('pageshow',event=>{if(event.persisted&&route().page==='training')render();});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&cameraStream){stopCamera();if(route().page==='training')render();}});
function devicesView(){
 const d=state.device,metrics=d.metrics||[],connected=!!(d.hasRecords||metrics.length),allowed=state.permissions.device;
 return `${head('从身体状态，读懂今天。','CONNECTED HEALTH')}
 <section class="card list"><button class="settingsrow" data-v2="apple-info"><span class="rowicon">${icon('watch')}</span><span class="rowmain"><strong>Apple Watch + iPhone</strong><small>当前可导入 Apple 健康记录</small></span>${icon('chev')}</button><button class="settingsrow" data-v2="garmin-info"><span class="rowicon">${icon('watch')}</span><span class="rowmain"><strong>Garmin + iPhone</strong><small>当前支持规范文件导入</small></span>${icon('chev')}</button></section>
 <section class="card device-hero"><div class="device-top"><span class="watch-visual">${icon('watch')}</span><div><p class="eyebrow">YOUR HEALTH DATA</p><h2>${esc(d.label)}</h2><span class="badge">${connected?'个人导入记录':'尚无设备记录'}</span></div></div><p class="subtle textbody">${esc(d.quality)}</p>${d.syncedAt?`<p class="micro">最近导入 ${esc(stamp(d.syncedAt))}</p>`:''}</section>
 <div class="health-grid">${metrics.map(m=>`<section class="health-tile"><span>${esc(m.label)}</span><b>${esc(m.value)}<small>${esc(m.unit)}</small></b><p class="${m.fresh===false?'stale':''}">${m.fresh===false?'历史记录 · 不作本次依据':'可用于上下文参考'}</p><small>${esc(m.source)}<br>${esc(stamp(m.at))}</small></section>`).join('')||'<div class="card empty-health"><h3>把已有的健康记录带进来</h3><p>导入后，每项记录的来源与时间都会显示在这里。</p></div>'}</div>
 ${section('添加健康记录')}<section class="card import-card"><div class="brand-row"><span>Apple Health</span><span>Garmin</span></div><h2>导入你自己的记录</h2><p class="subtle textbody">Apple 健康导出 XML / ZIP，或符合模板的 CSV / JSON。文件在本机服务处理；导入后会读取最近 30 天的可用记录。</p><input id="health-file" type="file" accept=".zip,.xml,.csv,.json" hidden><button class="btn primary wide" data-v2="import-health">选择健康文件 ${icon('upload')}</button><div class="device-links"><button class="linkbtn" data-v2="health-guide">怎么获取数据？</button><button class="linkbtn" data-v2="health-template">下载 CSV 模板</button></div><p class="micro">选择并导入即允许 Pivot 在计划调整时引用这些记录。文件导入不代表实时连接手表。</p><div id="health-status" role="status"></div></section>
 ${connected?`<form id="device-permission-form" class="card"><label class="settingsrow"><span class="rowmain"><strong>用于计划调整</strong><small>关闭后保留记录，停止向 Agent 提供数据</small></span><input class="toggle" name="allowed" type="checkbox" ${allowed?'checked':''}></label>${errorBox()}<button class="btn soft wide">保存数据使用设置</button></form><button class="linkbtn danger-link" data-v2="disconnect-health">清除已导入的健康记录</button>`:''}`;
}
async function importHealth(file){
 if(!file)return;if(file.size>100*1024*1024){notify('请使用100 MB以内的导出文件');return;}
 const b=$('[data-v2=import-health]'),status=$('#health-status');if(!navigator.onLine){const message='当前离线，健康记录尚未导入。恢复连接后重新选择文件。';if(status)status.textContent=message;notify(message);b.disabled=false;b.textContent='重新选择文件';return;}b.disabled=true;b.textContent='正在读取健康记录…';if(status)status.textContent='正在导入，请稍候。';
 try{
  const headers={'Content-Type':'application/octet-stream',[apiErrorFormatHeader]:'structured'};
  const res=await fetch('/api/wearable/import',{method:'POST',headers,body:file});
  const data=await res.json();
  if(!res.ok)throw apiResponseError(data,res.status,'导入失败');
  state=data;render();notify('健康记录已导入，可用于下一次调整。');
 }
 catch(e){const message=e instanceof TypeError?'连接中断，导入结果尚未确认。恢复连接后先查看记录，再决定是否重新导入。':e.message;if(status)status.textContent=message;notify(message);b.disabled=false;b.innerHTML='重新选择文件';}
}
function healthGuide(){showSheet(`<h2>获取你的穿戴记录</h2><ol><li><b>Apple Watch</b>：在 iPhone「健康」App 点击个人头像 → 导出所有健康数据，将导出的 ZIP 传到当前设备后选择导入。</li><li><b>Garmin</b>：从 Garmin 获取个人记录。将已有数据按本页 CSV 模板整理后导入，保留原设备名称与采集日期。</li></ol><p class="micro">本版先打通文件路径。Apple 原生 HealthKit 读取和 Garmin 账号自动同步需要原生应用／厂商授权，目前没有接入，不会显示为已连接。</p><button class="btn primary wide" data-v2="health-pick-from-guide">选择文件</button>`);}
document.addEventListener('change',e=>{if(e.target.id==='health-file')importHealth(e.target.files?.[0]);});
document.addEventListener('click',async e=>{const a=e.target.closest('[data-v2]')?.dataset.v2;if(!a)return;
 if(a==='import-health')$('#health-file').click();
 if(a==='health-guide'||a==='apple-info'||a==='garmin-info')healthGuide();
 if(a==='health-pick-from-guide'){closeSheet();$('#health-file').click();}
 if(a==='health-template'){const text='type,value,unit,date,source\nresting_hr,58,count/min,YYYY-MM-DDT07:00:00+08:00,填写实际设备名称\nhrv_sdnn,45,ms,YYYY-MM-DDT07:00:00+08:00,填写实际设备名称\nsleep,7.2,hours,YYYY-MM-DDT07:00:00+08:00,填写实际设备名称\n';const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='Pivot-健康记录模板.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('模板已下载，请填入真实记录与日期后导入。');}
 if(a==='disconnect-health')showSheet('<h2>清除健康记录？</h2><p class="textbody">清除导入的数据并停止引用。已保存的历史调整仍保留当时的依据摘要；设备端原始数据不受影响。</p><button class="btn danger wide" data-v2="confirm-disconnect" style="margin-top:20px">确认清除导入记录</button>');
 if(a==='confirm-disconnect')await mutation('wearable/disconnect',{},e.target,()=>{closeSheet();notify('导入记录已清除。');});
});
document.addEventListener('submit',async e=>{if(e.target.id!=='device-permission-form')return;e.preventDefault();await mutation('settings',{permissions:{device:new FormData(e.target).has('allowed')}},e.submitter,()=>notify('数据使用设置已保存。'));});
