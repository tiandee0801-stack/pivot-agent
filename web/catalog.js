/* Basketball training catalog on the existing same-origin Pivot API. */
'use strict';

const legacyTrainingView = trainingView;
const legacyEditPlan = editPlan;
const legacySessionView = sessionView;
const legacySessionRow = sessionRow;
const catalogPlaces = {home:'居家',gym:'健身房',court:'球场'};
const catalogUnits = {reps:'次',time:'秒',distance:'米',rounds:'回合'};
const catalogMetricMaximums = {reps:1000,time:14400,distance:50000,rounds:1000};
const emptyCatalogFilters = () => ({query:'',equipment:'',space:'',demo:false});
const catalogFilters = emptyCatalogFilters();
let catalogAbilityFilters = emptyCatalogFilters();
const catalogAbilities = [
 {id:'acceleration',title:'启动加速',icon:'arrow',actions:['short_acceleration','backpedal_turn']},
 {id:'braking',title:'减速变向',icon:'agent',actions:['linear_braking','lateral_shuffle_stop','angle_cut','cue_direction_change']},
 {id:'landing',title:'跳跃落地',icon:'goals',actions:['snap_down','jump_and_stick','lateral_hop_stick','ankle_pogo']},
 {id:'strength',title:'力量与稳定',icon:'training',actions:['squat','goblet_squat','dumbbell_rdl','band_rdl','split_squat','lateral_lunge','single_leg_balance','side_plank']},
];
const sceneImages = {
 home_band_full_body:'/assets/demos/band_row.jpg',
 gym_lower_body_core:'/assets/demos/dumbbell_rdl.jpg',
 court_footwork_braking:'/assets/court.jpg',
};
const catalogSelection = new Set();
const catalogPageSize = 12;
let catalogLimit = catalogPageSize;
let lastCatalogRoute = '';
const reviewNote = '预览内容 · 待体能教练审核';
const catalogCurrent = () => state?.trainingCatalog;
const catalogExercise = id => catalogCurrent()?.exercises.find(exercise=>exercise.id===id);
const catalogEquipment = item => item.equipment?.length ? item.equipment.join('、') : '徒手';
const catalogSpace = item => (item.space||[]).map(key=>catalogPlaces[key]||key).join(' / ');
const catalogCategoryRoute = name => name ? `training/category-${encodeURIComponent(name)}` : 'training/library';
const catalogCategories = () => [...new Set(catalogCurrent().exercises.map(exercise=>exercise.category))];
const catalogCategory = () => catalogCategories().find(name=>route().id===catalogCategoryRoute(name).split('/')[1])||'';
const catalogAbilityRoute = ability => `training/ability-${ability.id}`;
const catalogAbility = () => catalogAbilities.find(ability=>route().id===`ability-${ability.id}`);
const activeCatalogFilters = () => catalogAbility()?catalogAbilityFilters:catalogFilters;

try {
 const saved = JSON.parse(sessionStorage.getItem('pivot-catalog-browse')||'{}');
 for (const field of Object.keys(catalogFilters)) {
  if (typeof saved[field]===typeof catalogFilters[field]) catalogFilters[field] = saved[field];
 }
} catch {}

function preserveCatalogView() {
 if (catalogAbility()) return;
 try { sessionStorage.setItem('pivot-catalog-browse',JSON.stringify(catalogFilters)); } catch {}
}

function catalogDemo(id) {
 const item = typeof catalogDemoAssets==='undefined' ? null : catalogDemoAssets[id];
 return item && /^\/assets\/demos\/[\w.-]+\.(?:mp4|webm)$/.test(item.src) ? item : null;
}

function catalogDemoSection(exercise) {
 const demo = catalogDemo(exercise.id);
 if (!demo) return '';
 const poster = /^\/assets\/demos\/[\w.-]+\.(?:jpg|jpeg|png|webp)$/.test(demo.poster)
  ? ` poster="${esc(demo.poster)}"` : '';
 const link = (url,label) => typeof url==='string' && /^https:\/\//.test(url)
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label);
 const credits = [
  demo.sourceUrl ? link(demo.sourceUrl, demo.credit || '视频来源') : esc(demo.credit),
  link(demo.licenseUrl, demo.license),
 ].filter(Boolean);
 return `<section class="catalog-demo" aria-label="动作示范">
  <h3>${esc(demo.kind==='animated'?'3D 示范':demo.kind==='original-animation'?'自制动作动画':'动作示范')}</h3>
  <video class="catalog-demo-player" controls playsinline preload="metadata" aria-label="${esc(exercise.name)}动作示范" src="${esc(demo.src)}"${poster}></video>
  <p class="catalog-demo-error" hidden>视频暂时无法播放，可继续查看下方动作说明。</p>
  ${credits.length?`<p class="catalog-demo-credit">${credits.join(' · ')}</p>`:''}
  ${demo.notice?`<p class="catalog-demo-credit">${esc(demo.notice)}</p>`:''}
 </section>`;
}

function catalogActionList(actions,{template=null,returnToTraining=false}={}) {
 if (!actions?.length) return '';
 return `<ol class="catalog-action-list">${actions.map(action=>{
  const exercise = catalogExercise(action.exerciseId);
  const name = action.exerciseName || exercise?.name || action.exerciseId;
  const unit = catalogUnits[action.metric || exercise?.metric] || '';
  const demo = template && catalogDemo(action.exerciseId);
  return `<li><div class="catalog-action-line"><div><strong>${esc(name)}</strong><small>${esc(action.sets)} 组 × ${esc(action.quantity)} ${unit}${action.restSeconds ? ` · 组间 ${esc(action.restSeconds)} 秒` : ''}</small></div>
   ${demo?`<button class="linkbtn catalog-action-demo" type="button" data-catalog="template-demo" data-id="${esc(action.exerciseId)}" data-template="${esc(template.id)}" data-return-training="${returnToTraining}" aria-label="看${esc(name)}示范">${icon('video')} 看示范</button>`:''}</div></li>`;
 }).join('')}</ol>`;
}

function catalogExerciseCard(exercise) {
 const demo = catalogDemo(exercise.id);
 return `<button class="catalog-exercise" type="button" data-catalog="details" data-id="${esc(exercise.id)}">
  <span class="catalog-exercise-icon">${icon(demo?'video':'training')}</span>
  <span class="catalog-exercise-text"><strong>${esc(exercise.name)}</strong><small>${esc(exercise.category)} · ${esc(catalogEquipment(exercise))}</small></span>
  ${demo ? '<span class="catalog-video-badge">有示范</span>' : exercise.videoSupported ? '<span class="catalog-video-badge">可计数</span>' : ''}
  ${icon('chev')}
 </button>`;
}

function catalogFiltered(category,ability) {
 const {query,equipment,space,demo} = activeCatalogFilters();
 const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
 return catalogCurrent().exercises.filter(exercise=>{
  const searchable = [exercise.name,...(exercise.aliases||[]),exercise.category,exercise.goal,catalogEquipment(exercise)].join(' ').toLocaleLowerCase();
  return (!category || exercise.category===category) &&
    (!ability || ability.actions.includes(exercise.id)) &&
    (!equipment || (equipment==='徒手' ? !exercise.equipment.length : exercise.equipment.includes(equipment))) &&
    (!space || exercise.space.includes(space)) &&
    (!demo || catalogDemo(exercise.id)) && terms.every(term=>searchable.includes(term));
 });
}

function catalogFilterOptions(values,selected) {
 return values.map(([value,label])=>`<option value="${esc(value)}" ${selected===value?'selected':''}>${esc(label)}</option>`).join('');
}

function catalogExerciseResults(items) {
 if (!items.length) return '<p class="catalog-empty">没有找到匹配的动作，试试其他关键词或清除筛选。</p>';
 const remaining = items.length - catalogLimit;
 return items.slice(0,catalogLimit).map(catalogExerciseCard).join('') +
  (remaining>0?`<button class="btn soft catalog-more" type="button" data-catalog="more">查看更多 <small>还有 ${remaining} 个</small></button>`:'');
}

function catalogCategoryGrid() {
 const iconByCategory = ['clock','training','training','goals','shield','agent','arrow','watch'];
 const toneByCategory = ['mint','blue','blue','violet','mint','amber','violet','amber'];
 const exercises = catalogCurrent().exercises;
 return `<h2 class="catalog-browse-title">按类别浏览</h2>
  <div class="catalog-category-grid">${catalogCategories().map((name,index)=>`
   <button type="button" class="catalog-category" data-nav="${esc(catalogCategoryRoute(name))}" data-tone="${toneByCategory[index%toneByCategory.length]}">
    <span class="catalog-category-icon">${icon(iconByCategory[index%iconByCategory.length])}</span>
    <span><strong>${esc(name)}</strong><small>${exercises.filter(item=>item.category===name).length} 个动作</small></span>
    ${icon('chev')}
   </button>`).join('')}</div>`;
}

function catalogBrowseResults() {
 const category = catalogCategory();
 const ability = catalogAbility();
 const {query,equipment,space,demo} = activeCatalogFilters();
 if (!category && !ability && !query.trim() && !equipment && !space && !demo) {
  return catalogCategoryGrid();
 }
 const items = catalogFiltered(category,ability);
 return `<div class="catalog-results-heading"><h2>${query.trim()?'搜索结果':'训练动作'}</h2><span id="catalog-count" aria-live="polite">${items.length} 个动作</span></div>
  <div id="catalog-results" class="catalog-results">${catalogExerciseResults(items)}</div>`;
}

function catalogFilterChips() {
 const filters = activeCatalogFilters();
 const labels = [
  ['equipment',filters.equipment],
  ['space',catalogPlaces[filters.space]],
  ['demo',filters.demo?'有示范视频':''],
 ].filter(([,name])=>name);
 return labels.map(([key,name])=>`<button type="button" data-catalog="remove-filter" data-id="${key}" aria-label="取消筛选：${esc(name)}">${esc(name)} <span aria-hidden="true">×</span></button>`).join('');
}

function catalogFilterCount() {
 const {equipment,space,demo} = activeCatalogFilters();
 return Number(!!equipment) + Number(!!space) + Number(demo);
}

function refreshCatalogResults() {
 const content = $('#catalog-browse-results');
 if (!content) return;
 content.innerHTML = catalogBrowseResults();
 $('#catalog-active-filters').innerHTML = catalogFilterChips();
 const count = catalogFilterCount();
 $('#catalog-filter-button').innerHTML = count ? `筛选 <small>${count}</small>` : '筛选';
}

function catalogOpenFilters() {
 const filters = activeCatalogFilters();
 const gear = ['徒手',...new Set(catalogCurrent().exercises.flatMap(item=>item.equipment))];
 const hasDemo = catalogCurrent().exercises.some(item=>catalogDemo(item.id));
 showSheet(`<h2>筛选动作</h2><form id="catalog-filter-form">
  ${catalogAbility()?'':`<label class="field">类别<select name="category"><option value="">不限类别</option>${catalogFilterOptions(catalogCategories().map(category=>[category,category]),catalogCategory())}</select></label>`}
  <label class="field">器械<select name="equipment"><option value="">不限器械</option>${catalogFilterOptions(gear.map(item=>[item,item]),filters.equipment)}</select></label>
  <label class="field">场地<select name="space"><option value="">不限场地</option>${catalogFilterOptions(Object.entries(catalogPlaces),filters.space)}</select></label>
  ${hasDemo?`<label class="check"><input type="checkbox" name="demo" ${filters.demo?'checked':''}>只看有示范视频的动作</label>`:''}
  <div class="catalog-filter-actions">
   <button type="button" class="btn soft" data-catalog="reset-filters">重置筛选</button>
   <button type="submit" class="btn primary">应用筛选</button>
  </div>
 </form>`);
}

function catalogLibraryPanel() {
 const category = catalogCategory();
 const ability = catalogAbility();
 const count = catalogFilterCount();
 return `<section class="catalog-library" aria-label="训练动作库">
   <button class="back" type="button" data-nav="${category?'training/library':'training'}">${icon('back')}${category?'返回动作库':'返回训练'}</button>
   <div class="catalog-page-heading"><h1>${esc(ability?.title || category || '动作库')}</h1>${catalogSelection.size?`<button class="btn soft catalog-selected" type="button" data-catalog="record">已选 ${catalogSelection.size} 项 ${icon('chev')}</button>`:''}</div>
   <div class="catalog-searchbar">
    <label class="hidden" for="catalog-search">搜索动作</label>
    <input id="catalog-search" type="search" inputmode="search" autocomplete="off" value="${esc(activeCatalogFilters().query)}" placeholder="${ability?'搜索本组动作':'搜索动作，如划船、落地'}">
    <button type="button" id="catalog-filter-button" class="btn soft" data-catalog="filters">筛选${count?` <small>${count}</small>`:''}</button>
   </div>
   <div id="catalog-active-filters" class="catalog-active-filters" aria-label="已选筛选">${catalogFilterChips()}</div>
   <div id="catalog-browse-results">${catalogBrowseResults()}</div>
  </section>`;
}

function catalogTemplatePanel({onHome=false}={}) {
 return `<section${onHome?' class="training-discovery" aria-labelledby="training-scenes-title"':' aria-label="训练模板"'}>
  ${onHome?'<h2 id="training-scenes-title">按场景选训练</h2>':''}
  <div class="catalog-template-list${onHome?' training-scene-list':''}">
   ${catalogCurrent().templates.map(template=>`<button class="catalog-template" type="button" data-catalog="template" data-id="${esc(template.id)}">
    ${onHome && sceneImages[template.id]?`<img class="training-scene-image" src="${esc(sceneImages[template.id])}" alt="" loading="lazy" width="72" height="65">`:`<span class="catalog-template-icon">${icon(template.space.includes('court')?'goals':'training')}</span>`}
    <span class="catalog-template-title"><strong>${esc(template.title)}</strong><small>${onHome?'':`${esc(catalogSpace(template))} · `}${esc(template.minutes)} 分钟 · ${template.actions.length} 个动作</small>${onHome?`<small>${esc(catalogEquipment(template))}</small>`:''}</span>
    ${icon('chev')}
   </button>`).join('')}
  </div>
 </section>`;
}

function catalogAbilityPanel() {
 return `<section class="training-discovery" aria-labelledby="training-abilities-title">
  <h2 id="training-abilities-title">按篮球能力找动作</h2>
  <div class="training-ability-grid">${catalogAbilities.map(ability=>{
   const count = ability.actions.filter(catalogExercise).length;
   return count?`<button class="training-ability" type="button" data-nav="${catalogAbilityRoute(ability)}">
    <span class="catalog-category-icon">${icon(ability.icon)}</span>
    <span><strong>${esc(ability.title)}</strong><small>${count} 个动作</small></span>${icon('chev')}
   </button>`:'';
  }).join('')}</div>
  </section>`;
}

trainingView = function() {
 const catalog = catalogCurrent();
 if (!catalog) return legacyTrainingView();
 const {id} = route();
 if (id!==lastCatalogRoute) {
  lastCatalogRoute = id;
  catalogLimit = catalogPageSize;
  catalogAbilityFilters = emptyCatalogFilters();
 }
 if (id==='video') return `<button class="back" type="button" data-nav="training">${icon('back')}返回训练</button>${legacyTrainingView()}`;
 if (id==='templates') return `<button class="back" type="button" data-nav="training">${icon('back')}返回训练</button><div class="catalog-page-heading"><h1>训练模板</h1></div>${catalogTemplatePanel()}`;
 if (id==='workout') return workoutView();
 if (id==='library'||catalogCategory()||catalogAbility()) return catalogLibraryPanel();
 return `<header class="catalog-hero">
   <span class="catalog-preview"><i></i>${reviewNote}</span>
   <h1>篮球体能训练</h1>
  </header>
  <div class="catalog-entry-grid">
   <button class="catalog-entry" type="button" data-nav="training/library"><span class="catalog-entry-icon">${icon('training')}</span><strong>动作库</strong><small>${catalog.exercises.length} 个动作 · 按类别浏览</small>${icon('chev')}</button>
   <button class="catalog-entry catalog-entry-templates" type="button" data-nav="training/templates"><span class="catalog-entry-icon">${icon('today')}</span><strong>训练模板</strong><small>${catalog.templates.length} 套场景训练</small>${icon('chev')}</button>
  </div>
  <div class="catalog-primary-actions">
   <button class="btn primary" type="button" data-catalog="record">${icon('edit')} 记录训练${catalogSelection.size?` <span aria-label="已选 ${catalogSelection.size} 个动作">${catalogSelection.size}</span>`:''}</button>
   <button class="btn soft" type="button" data-nav="training/video">${icon('video')} 视频计数</button>
  </div>
  ${nextWorkoutCard()}
  ${workoutDemoStrip()}
  ${weeklyActivityCard()}
  ${catalogTemplatePanel({onHome:true})}
  ${catalogAbilityPanel()}`;
};

function catalogExerciseDetails(exercise,{template=null,returnToTraining=false}={}) {
 const alternatives = (exercise.alternatives||[]).map(item=>typeof item==='string'?item:item.exerciseId)
  .map(catalogExercise).filter(Boolean);
 const instructions = [exercise.instructions].flat().filter(Boolean);
 showSheet(`<h2>${esc(exercise.name)}</h2>
   <p class="catalog-sheet-note">${reviewNote}</p>
   ${catalogDemoSection(exercise)}
   ${template?`<button class="linkbtn catalog-demo-back" type="button" data-catalog="template" data-id="${esc(template.id)}" data-return-training="${returnToTraining}">${icon('back')} 返回模板</button>`:''}
   <div class="catalog-detail-tags"><span>${esc(exercise.category)}</span><span>${esc(exercise.level)}</span><span>${esc(catalogEquipment(exercise))}</span><span>${esc(catalogSpace(exercise))}</span></div>
   <p class="textbody">${esc(exercise.goal)}</p>
   ${instructions.length?`<ul class="catalog-instructions">${instructions.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`:''}
   ${exercise.anchorRequired?'<p class="notice warn">这个动作需要合适的固定点。</p>':''}
   ${alternatives.length?`<details><summary>相关动作</summary><div class="catalog-results">${alternatives.map(catalogExerciseCard).join('')}</div></details>`:''}
   <div class="catalog-sheet-actions">
    <button class="btn primary" type="button" data-catalog="log-exercise" data-id="${esc(exercise.id)}">${catalogSelection.has(exercise.id)?'从本次训练移除':'加入本次训练'}</button>
    <button class="btn soft" type="button" data-catalog="add-to-plan" data-id="${esc(exercise.id)}">加入当前计划</button>
    ${exercise.videoSupported?`<button class="linkbtn" type="button" data-exercise="${esc(exercise.id)}">${icon('video')} 视频计数</button>`:''}
   </div>`);
}

function catalogNumberField(label,name,value,min,max,{optional=false,step=1}={}) {
 return `<label class="field">${label}<input type="number" name="${name}" value="${esc(value??'')}" min="${min}" max="${max}" step="${step}" inputmode="${step===1?'numeric':'decimal'}" ${optional?'':'required'}></label>`;
}

function catalogAddControl(type,actions,label) {
 const actionIds = new Set(actions.map(action=>action.exerciseId));
 const items = catalogCurrent().exercises.filter(exercise=>!actionIds.has(exercise.id));
 return `<div class="catalog-add-row" data-catalog-add>
  <label class="field">${label}<select name="addExercise"><option value="">选择动作</option>${catalogFilterOptions(items.map(item=>[item.id,item.name]),'')}</select></label>
  <button type="button" class="btn soft" data-catalog="${type}">添加</button>
 </div>`;
}

function catalogPlanRow(action) {
 const exercise = catalogExercise(action.exerciseId);
 const metric = exercise?.metric||action.metric;
 const quantity = {reps:'每组次数',time:'每组秒数',distance:'每组米数',rounds:'每组回合'};
 return `<li class="catalog-edit-row" data-exercise-id="${esc(action.exerciseId)}">
  <div class="catalog-edit-head"><strong>${esc(exercise?.name||action.exerciseName||action.exerciseId)}</strong>
   <div><button class="catalog-icon-btn" type="button" data-catalog="move-up" aria-label="上移">↑</button>
    <button class="catalog-icon-btn" type="button" data-catalog="move-down" aria-label="下移">↓</button>
    <button class="catalog-icon-btn" type="button" data-catalog="remove-row" aria-label="移除动作">${icon('trash')}</button></div>
  </div>
  <div class="formgrid">${catalogNumberField('组数','sets',action.sets,1,20)}
   ${catalogNumberField(quantity[metric]||'数量','quantity',action.quantity,1,catalogMetricMaximums[metric]||1000)}
   ${catalogNumberField('组间休息（秒）','restSeconds',action.restSeconds,0,600,{optional:true})}</div>
 </li>`;
}

function catalogPlanEquipment(ids) {
 const gear = [...new Set(ids.flatMap(id=>catalogExercise(id)?.equipment||[]))];
 return gear.join('、')||'徒手';
}

function catalogTemplateDetails(template,returnToTraining=false) {
 const usesAnchor = template.actions.some(action=>catalogExercise(action.exerciseId)?.anchorRequired);
 showSheet(`<h2>${esc(template.title)}</h2><p class="catalog-sheet-note">${reviewNote}</p>
  <div class="catalog-detail-tags"><span>${esc(catalogSpace(template))}</span><span>${esc(template.minutes)} 分钟</span><span>${esc(catalogEquipment(template))}</span></div>
  <p class="textbody">${esc(template.purpose)}</p>
  ${usesAnchor?'<p class="notice warn">部分动作需要合适的弹力带固定点。</p>':''}
  ${catalogActionList(template.actions,{template,returnToTraining})}
  <div class="catalog-sheet-actions"><button class="btn primary wide" type="button" data-catalog="edit-template" data-id="${esc(template.id)}" data-return-training="${returnToTraining}">采用并编辑计划 ${icon('arrow')}</button></div>`);
}

function catalogPlanEditor(template=null, extra=null, returnToTraining=false) {
 const plan = state.plan;
 const chosen = template||plan;
 const actions = [...(chosen.actions||[])];
 if(extra && !actions.some(item=>item.exerciseId===extra.id)) actions.push({exerciseId:extra.id});
 const space = Array.isArray(chosen.space)?chosen.space[0]:chosen.space;
 const gear = catalogPlanEquipment(actions.map(action=>action.exerciseId));
 showSheet(`<h2>${template?'采用训练模板':'编辑训练计划'}</h2><p class="catalog-sheet-note">${reviewNote}</p>
  <form id="catalog-plan-form" data-version="${esc(plan.version)}" data-template="${esc(template?.id||plan.templateId||'')}" data-return-training="${returnToTraining}">
   <label class="field">训练名称<input name="title" required maxlength="100" value="${esc(chosen.title)}"></label>
   <div class="formgrid">
    <label class="field">日期<input type="date" name="date" min="${todayISO()}" value="${esc(plan.date>=todayISO()?plan.date:todayISO())}" required></label>
    <label class="field">开始时间<input type="time" name="time" value="${esc(plan.time)}" required></label>
    ${catalogNumberField('计划分钟','minutes',chosen.minutes,1,240)}
    <label class="field">训练场地<select name="space"><option value="">暂未填写</option>${catalogFilterOptions(Object.entries(catalogPlaces),space)}</select></label>
   </div>
   <label class="field">训练目标<input name="purpose" maxlength="120" value="${esc(chosen.purpose||'')}"></label>
   <label class="field">动作所需器械<input name="equipment" value="${esc(gear)}" readonly></label>
   <h3 class="catalog-form-heading">训练动作顺序</h3>
   <ol class="catalog-edit-list" data-catalog-rows>${actions.map(catalogPlanRow).join('')}</ol>
   ${catalogAddControl('append-plan',actions,'添加计划动作')}
   <label class="field">计划说明（选填）<textarea name="content" maxlength="1500" rows="2">${esc(chosen.content||'')}</textarea></label>
   ${errorBox()}<button type="submit" class="btn primary wide">确认并保存计划 ${icon('check')}</button>
  </form>`);
}

editPlan = function() {
 if (catalogCurrent() && state.plan.actions?.length) return catalogPlanEditor();
 return legacyEditPlan();
};

function catalogActualFields(entry, metric) {
 const fields = metric==='reps' ? [
  catalogNumberField('组数','sets',entry.sets,1,20),
  catalogNumberField('总次数','reps',entry.reps,1,1000),
  catalogNumberField('重量 kg（选填）','weight',entry.weight,0,500,{optional:true,step:.1}),
 ] : [
  ...((metric==='distance'||metric==='rounds')?[catalogNumberField(metric==='distance'?'距离（米）':'回合',metric==='distance'?'distanceMeters':'rounds',metric==='distance'?entry.distanceMeters:entry.rounds,1,catalogMetricMaximums[metric])]:[]),
  catalogNumberField(metric==='time'?'用时（秒）':'用时（秒，可选）','seconds',entry.seconds,1,14400,{optional:metric!=='time'}),
  ...(metric==='distance'?[catalogNumberField('回合（选填）','rounds',entry.rounds,1,catalogMetricMaximums.rounds,{optional:true})]:[]),
  ...(metric==='rounds'?[catalogNumberField('距离（米，可选）','distanceMeters',entry.distanceMeters,1,catalogMetricMaximums.distance,{optional:true})]:[]),
 ];
 return fields.join('');
}

function catalogRecordRow(entry) {
 const exercise = catalogExercise(entry.exerciseId);
 const metric = exercise?.metric||entry.metric;
 return `<li class="catalog-edit-row" data-exercise-id="${esc(entry.exerciseId)}">
  <div class="catalog-edit-head"><strong>${esc(entry.exerciseName||exercise?.name||entry.exerciseId)}</strong>
   <button class="catalog-icon-btn" type="button" data-catalog="remove-row" aria-label="移除动作">${icon('trash')}</button>
  </div>
  <div class="formgrid">${catalogActualFields(entry, metric)}</div>
 </li>`;
}

function catalogRecordEditor({actions=[],session=null,taskId='',fromSelection=false}={}) {
 const entries = session?.exerciseEntries||actions.map(action=>({exerciseId:action.exerciseId}));
 showSheet(`<h2>${session?'编辑训练记录':'记录本次训练'}</h2>
  <form id="catalog-record-form" data-key="${esc(uid())}" data-id="${esc(session?.id||'')}" data-revision="${esc(session?.revision||'')}" data-task="${esc(taskId)}" data-selection="${fromSelection}">
   <div class="formgrid">
    <label class="field">日期<input type="date" name="performedAt" max="${todayISO()}" value="${esc(session?.performedAt||todayISO())}" required></label>
    ${catalogNumberField('实际训练分钟','minutes',session?.minutes,session?.completion==='not_done'?0:1,240)}
    <label class="field">完成情况<select name="completion" required><option value="">请选择</option>${catalogFilterOptions(Object.entries(completionNames),session?.completion)}</select></label>
    <label class="field">训练感受<select name="feeling" required><option value="">请选择</option>${catalogFilterOptions(['合适','偏累','偏轻松','不合适'].map(item=>[item,item]),session?.feeling)}</select></label>
   </div>
   <fieldset name="exerciseDetails" class="catalog-record-actions" ${session?.completion==='not_done'?'hidden disabled':''}>
    <legend>实际完成的动作</legend>
    <p class="micro">按实际完成填写。没有做的动作可以移除。</p>
    <ol class="catalog-edit-list" data-catalog-rows>${entries.map(catalogRecordRow).join('')}</ol>
    ${catalogAddControl('append-record',entries,'添加已完成的动作')}
   </fieldset>
   <label class="check"><input type="checkbox" name="discomfort" ${session?.discomfort?'checked':''}>训练中出现了身体不适</label>
   <label class="field">训练备注（选填）<textarea name="note" maxlength="450" rows="2">${esc(session?.note||'')}</textarea></label>
   ${errorBox()}<button type="submit" class="btn primary wide">保存训练记录 ${icon('check')}</button>
  </form>`);
}

function catalogValue(form,key) {
 return form.elements.namedItem(key)?.value||'';
}

function catalogReadActions(form) {
 return [...form.querySelectorAll('[data-exercise-id]')].map(row=>({
  exerciseId:row.dataset.exerciseId,
  sets:Number(row.querySelector('[name="sets"]').value),
  quantity:Number(row.querySelector('[name="quantity"]').value),
  restSeconds:Number(row.querySelector('[name="restSeconds"]').value),
 }));
}

function catalogReadEntries(form) {
 return [...form.querySelectorAll('[data-exercise-id]')].map(row=>{
  const fields = [...row.querySelectorAll('input[name]')].filter(input=>input.value!=='');
  return {exerciseId:row.dataset.exerciseId,...Object.fromEntries(fields.map(input=>[input.name,Number(input.value)]))};
 });
}

sessionRow = function(session) {
 if (!session.exerciseEntries?.length) return legacySessionRow(session);
 return `<button class="row" data-nav="session/${esc(session.id)}"><span class="rowicon">${icon('training')}</span>
  <span class="rowmain"><strong>${esc(session.exerciseEntries.map(entry=>entry.exerciseName).slice(0,2).join('、')||'训练记录')}</strong>
  <small>${esc(session.performedAt)} · ${session.exerciseEntries.length} 个动作 · ${esc(session.minutes)} 分钟</small></span>${icon('chev')}</button>`;
};

sessionView = function() {
 const session = currentSession();
 if (!session?.exerciseEntries || session.observation) return legacySessionView();
 const selected = (state.history||[]).find(task=>task.id===session.taskId && task.receipt?.planSaved);
 return `<button class="back" type="button" data-nav="history">${icon('back')}返回记录</button>${head('训练记录',dateLabel(session.performedAt))}
  <section class="card"><div class="saved-badges"><span class="badge">${esc(completionNames[session.completion])}</span><span class="badge neutral">${esc(session.feeling)}</span></div>
  <div class="saved-duration">${esc(session.minutes)}<small>分钟 · ${session.exerciseEntries.length} 个动作</small></div>
  <p class="micro">${session.discomfort?'本次记录有身体不适':'本次未报告身体不适'}</p>
  ${session.note?`<p class="textbody">${esc(session.note)}</p>`:''}</section>
  ${session.exerciseEntries.length?`<section class="card catalog-history"><h2>实际完成</h2><ol class="catalog-action-list">
   ${session.exerciseEntries.map(entry=>{
    const metrics = [['sets','组'],['reps','次'],['weight','kg'],['seconds','秒'],['distanceMeters','米'],['rounds','回合']];
    return `<li><strong>${esc(entry.exerciseName||catalogExercise(entry.exerciseId)?.name||entry.exerciseId)}</strong>
     <small>${metrics.filter(([name])=>entry[name]!=null).map(([name,unit])=>`${esc(entry[name])} ${unit}`).join(' · ')}</small></li>`;
   }).join('')}</ol></section>`:''}
  ${workoutHistoryOutcomes(session)}
  ${selected?`<button type="button" class="linkbtn" data-nav="task/${esc(selected.id)}">查看关联计划 ${icon('chev')}</button>`:''}
  <div class="actions"><button class="btn soft" type="button" data-catalog="edit-record">编辑记录</button>${button('delete-record','删除记录','danger')}</div>`;
};

document.addEventListener('input',event=>{
 if (event.target.id==='catalog-search') {
  activeCatalogFilters().query = event.target.value;
  catalogLimit = catalogPageSize;
  preserveCatalogView();
  refreshCatalogResults();
 }
});

$('#sheet').addEventListener('close',()=>{
 if (!$('#sheet').open) $('#sheet .catalog-demo-player')?.pause();
});

document.addEventListener('error',event=>{
 const video = event.target;
 if (video instanceof HTMLVideoElement && video.classList.contains('catalog-demo-player')) {
  video.hidden = true;
  video.nextElementSibling.hidden = false;
 }
},true);

document.addEventListener('change',event=>{
 const {target} = event;
 if (target.form?.id==='catalog-record-form' && target.name==='completion') {
  const detail = target.form.elements.exerciseDetails;
  detail.disabled = detail.hidden = target.value==='not_done';
 }
});

document.addEventListener('click',event=>{
 const control = event.target.closest('button[data-catalog]');
 if (!control || busy || !catalogCurrent()) return;
 const {catalog,id,task} = control.dataset;
 const exercise = catalogExercise(id);
 const template = catalogCurrent().templates.find(item=>item.id===id);
 const form = control.closest('form');
 const rows = form?.querySelector('[data-catalog-rows]');
 const row = control.closest('[data-exercise-id]');
 if (control.closest('#sheet-body')) $('#sheet .catalog-demo-player')?.pause();
 if (catalog==='filters') catalogOpenFilters();
 if (catalog==='reset-filters' && form?.id==='catalog-filter-form') {
  for (const field of form.querySelectorAll('select')) field.value = '';
  if (form.elements.demo) form.elements.demo.checked = false;
 }
 if (catalog==='remove-filter' && ['equipment','space','demo'].includes(id)) {
  activeCatalogFilters()[id] = id==='demo'?false:'';
  catalogLimit = catalogPageSize;
  preserveCatalogView();
  refreshCatalogResults();
  $('#catalog-filter-button')?.focus({preventScroll:true});
 }
 if (catalog==='more') {
  const previous = catalogLimit;
  catalogLimit += catalogPageSize;
  refreshCatalogResults();
  document.querySelectorAll('#catalog-results .catalog-exercise')[previous]?.focus();
 }
 if (catalog==='details' && exercise) catalogExerciseDetails(exercise);
 if (catalog==='template-demo' && exercise) {
  const from = catalogCurrent().templates.find(item=>item.id===control.dataset.template);
  catalogExerciseDetails(exercise,{template:from,returnToTraining:control.dataset.returnTraining==='true'});
 }
 if (catalog==='template' && template) catalogTemplateDetails(template,control.dataset.returnTraining==='true'||!!control.closest('.training-scene-list'));
 if (catalog==='edit-template' && template) catalogPlanEditor(template,null,control.dataset.returnTraining==='true');
 if (catalog==='add-to-plan' && exercise) catalogPlanEditor(null,exercise);
 if (catalog==='log-exercise' && exercise) {
  if (catalogSelection.has(exercise.id)) {
   catalogSelection.delete(exercise.id);
   notify('已从本次训练移除。');
  } else {
   catalogSelection.add(exercise.id);
   notify('已加入本次训练。可以继续选动作。');
  }
  closeSheet();
  render();
  document.querySelector(`[data-catalog="details"][data-id="${CSS.escape(exercise.id)}"]`)?.focus({preventScroll:true});
 }
 if (catalog==='record') catalogRecordEditor({actions:[...catalogSelection].map(exerciseId=>({exerciseId})),fromSelection:true});
 if (catalog==='edit-record') catalogRecordEditor({session:currentSession()});
 if (catalog==='record-plan') {
  const linked = (state.history||[]).find(item=>item.id===task && item.receipt?.planSaved);
  const actions = linked?.options?.find(option=>option.id===linked.selectedId)?.actions || state.plan.actions || [];
  catalogRecordEditor({actions,taskId:linked?.id||''});
 }
 if (catalog==='move-up' && row?.previousElementSibling) rows.insertBefore(row,row.previousElementSibling);
 if (catalog==='move-down' && row?.nextElementSibling) rows.insertBefore(row.nextElementSibling,row);
 if (catalog==='remove-row' && row) {
  const available = form.elements.addExercise;
  if (available && ![...available.options].some(option=>option.value===row.dataset.exerciseId)) {
   const exercise = catalogExercise(row.dataset.exerciseId);
   if (exercise) available.add(new Option(exercise.name,exercise.id));
  }
  row.remove();
  available?.focus({preventScroll:true});
 }
 if (catalog==='append-plan' || catalog==='append-record') {
  const choice = form.elements.addExercise;
  const selected = catalogExercise(choice.value);
  if (!selected) { choice.focus(); return; }
  const entry = {exerciseId:selected.id};
  rows.insertAdjacentHTML('beforeend',catalog==='append-plan'?catalogPlanRow(entry):catalogRecordRow(entry));
  choice.remove(choice.selectedIndex);
  rows.lastElementChild.querySelector('input')?.focus();
 }
 if (form?.id==='catalog-plan-form' && (catalog==='append-plan'||catalog==='remove-row')) {
  form.elements.equipment.value = catalogPlanEquipment([...rows.children].map(item=>item.dataset.exerciseId));
 }
});

document.addEventListener('submit',async event=>{
 const form = event.target;
 if (form.id==='catalog-filter-form') {
  event.preventDefault();
  const filters = activeCatalogFilters();
  filters.equipment = form.elements.equipment.value;
  filters.space = form.elements.space.value;
  filters.demo = form.elements.demo?.checked || false;
  catalogLimit = catalogPageSize;
  preserveCatalogView();
  const ability = catalogAbility();
  const path = ability?catalogAbilityRoute(ability):catalogCategoryRoute(form.elements.category.value);
  closeSheet();
  if (location.hash==='#'+path) refreshCatalogResults();
  else go(path);
  return;
 }
 if (busy || !['catalog-plan-form','catalog-record-form'].includes(form.id)) return;
 event.preventDefault();
 if (form.id==='catalog-plan-form') {
  const actions = catalogReadActions(form);
  if (!actions.length) { displayError(new Error('请至少保留一个计划动作。'),form); return; }
  const templateId = form.dataset.template;
  await mutation('plan',{
   expectedVersion:Number(form.dataset.version), title:catalogValue(form,'title').trim(), date:catalogValue(form,'date'), time:catalogValue(form,'time'),
   minutes:Number(catalogValue(form,'minutes')), purpose:catalogValue(form,'purpose'), content:catalogValue(form,'content'),
   equipment:catalogValue(form,'equipment'), space:catalogValue(form,'space'), actions, ...(templateId&&{templateId}),
  },event.submitter,()=>{
   closeSheet();
   notify('带动作清单的训练计划已保存。');
   if (form.dataset.returnTraining==='true') {
    requestAnimationFrame(()=>$('.workout-next button')?.focus());
   } else go('today');
  });
  return;
 }
 const completion = catalogValue(form,'completion');
 const entries = completion==='not_done'?[]:catalogReadEntries(form);
 if (completion!=='not_done' && !entries.length) { displayError(new Error('请添加实际完成的动作。'),form); return; }
 const payload = {
  completion, minutes:completion==='not_done'?0:Number(catalogValue(form,'minutes')),
  feeling:catalogValue(form,'feeling'), discomfort:form.elements.discomfort.checked,
  note:catalogValue(form,'note'), performedAt:catalogValue(form,'performedAt'),
  exerciseEntries:entries,
 };
 const id = form.dataset.id;
 if (id) Object.assign(payload,{id,expectedRevision:Number(form.dataset.revision)});
 else Object.assign(payload,{idempotencyKey:form.dataset.key,...(form.dataset.task&&{taskId:form.dataset.task})});
 await mutation(id?'sessions/update':'sessions',payload,event.submitter,()=>{
  if (form.dataset.selection==='true') catalogSelection.clear();
  closeSheet();
  notify('本次训练记录已保存。');
  const saved = state.savedSessionId || id;
  go(saved?'session/'+saved:'history');
 });
});
