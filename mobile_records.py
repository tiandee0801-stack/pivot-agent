"""Transactional mobile records. Original model observations remain immutable."""
import hashlib
import json
import math
import re
import uuid
import analytics
import training_catalog as training
from datetime import date


def helpers():
    from engine import RequestError, stamp, string, integer, boolean, encode
    return RequestError, stamp, string, integer, boolean, encode


def initialize(db, ctx):
    db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS video_jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS operations(key TEXT PRIMARY KEY,hash TEXT NOT NULL,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS operation_recoveries(key TEXT PRIMARY KEY,hash TEXT NOT NULL)')
    from engine import ALT_PLANS
    ctx.setdefault('alternatives', [dict(x) for x in ALT_PLANS])
    ctx.setdefault('weeklyGoal', 3)
    ctx.setdefault('profileConfirmed', False)
    if ctx.get('sessionProvenanceVersion') != 1 or 'recentSessions' not in ctx:
        collect_recent_sessions(db, ctx)


def is_example_session(record):
    if ((record.get('note') or '').startswith('[示例体验反馈]')
            or record.get('exerciseName') == '示例训练反馈'):
        return True
    # Older versions inherited the demo plan's flag for independent ball logs.
    if record.get('exercise') == 'basketball' and not record.get('taskId'):
        return False
    return bool(record.get('example'))


def all_records(db, table):
    if table not in ('sessions', 'video_jobs'):
        raise ValueError('table')
    records = [json.loads(r[0]) for r in db.execute(f'SELECT data FROM {table} ORDER BY rowid DESC')]
    if table == 'sessions':
        for record in records:
            record['example'] = is_example_session(record)
    return records


def state_extra(db, ctx):
    jobs = []
    for job in all_records(db, 'video_jobs'):
        result = job.get('result')
        if result:
            job = dict(job, result={k:v for k,v in result.items() if k not in ('frames','events')})
        jobs.append(job)
    return {'sessions': all_records(db,'sessions'), 'videoJobs':jobs, 'weeklyGoal':ctx['weeklyGoal'],'exerciseGoals':ctx.get('exerciseGoals',{}),'trainingPreferences':ctx.get('trainingPreferences',{})}


def operation(db, body, path):
    E, _, string, _, _, _ = helpers()
    key = string(body,'idempotencyKey',128,True)
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',key):
        raise E('操作编号格式不正确。')
    payload = {k:v for k,v in body.items() if k != 'idempotencyKey' and not k.startswith('_')}
    digest = hashlib.sha256((path+json.dumps(payload,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
    row = db.execute('SELECT hash,data FROM operations WHERE key=?',(key,)).fetchone()
    if row:
        if row[0] != digest:
            raise E('此操作编号已用于另一份内容，请刷新后重试。','idempotency_conflict',409)
        return key,digest,json.loads(row[1])
    reserved = db.execute('SELECT hash FROM operation_recoveries WHERE key=?',(key,)).fetchone()
    if reserved and reserved[0] != digest:
        raise E('此操作编号已用于另一份内容，请刷新后重试。','idempotency_conflict',409)
    return key,digest,None


def lookup_operation(db, ident):
    E, *_ = helpers()
    row=db.execute('SELECT data FROM operations WHERE key=?',(ident,)).fetchone()
    if row:
        return json.loads(row[0])
    operations = [json.loads(data) for data, in db.execute('SELECT data FROM operations ORDER BY rowid')]
    for obj in operations:
        if obj.get('operationId') == ident:
            return obj
    # Early releases generated one number on the task and a different one
    # when indexing the receipt. Recognize the old task number as an alias.
    if re.fullmatch(r'[0-9a-f]{32}', ident):
        for data, in db.execute('SELECT data FROM tasks'):
            task = json.loads(data)
            receipt = task.get('receipt') or {}
            if receipt.get('operationId') == ident:
                linked = next((op for op in operations if op.get('taskId') == task['id']
                               and op.get('planVersion') == receipt.get('planVersion')), None)
                if linked:
                    return linked
                break
    raise E('尚无已完成的操作回执，请核对原请求。','not_found',404)


def reserve_operation_recovery(db,key,digest,task_id):
    db.execute('INSERT OR IGNORE INTO operation_recoveries VALUES(?,?)',(key,digest))
    return {'status':'not_submitted','idempotencyKey':key,'taskId':task_id}


def remember_operation(db,key,digest,fields,*,operation_id=None,at=None):
    _,stamp,_,_,_,encode=helpers()
    obj={'operationId':operation_id or uuid.uuid4().hex,'idempotencyKey':key,
         'status':'succeeded','at':at or stamp(),**fields}
    db.execute('INSERT INTO operations VALUES(?,?,?)',(key,digest,encode(obj)))
    db.execute('DELETE FROM operation_recoveries WHERE key=?',(key,))
    return obj


def collect_recent_sessions(db, ctx):
    sessions=all_records(db,'sessions')
    sessions.sort(key=lambda r:(r['performedAt'],r.get('createdAt','')), reverse=True)
    # Keep separate short histories so a test record cannot crowd out a
    # person's most recent real record or vice versa.
    ctx['recentSessions']=[r for r in sessions if not r['example']][:5]+[r for r in sessions if r['example']][:5]
    ctx['sessionProvenanceVersion'] = 1


def refresh_context(db,ctx):
    collect_recent_sessions(db, ctx)
    ctx['contextVersion']+=1


def edit_plan(ctx,body):
    E,stamp,string,integer,_,_=helpers()
    if integer(body.get('expectedVersion'),1,2**31-1)!=ctx['plan']['version']:
        raise E('计划已更新，请刷新后再保存。','stale_plan',409)
    if not ctx['permissions']['save']:
        raise E('请先开启保存计划权限。','save_denied',403)
    title=string(body,'title',100,True)
    day=string(body,'date',10,True)
    clock=string(body,'time',5,True)
    try:
        parsed=date.fromisoformat(day)
        if str(parsed)!=day or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',clock):
            raise ValueError
    except ValueError:
        raise E('请填写有效日期与时间。')
    if parsed < date.today():
        raise E('计划日期不能早于今天。')
    minutes = integer(body.get('minutes'),1,240)
    action_patch = training.plan_patch(body, ctx['plan'])
    actions = action_patch.get('actions', ctx['plan'].get('actions', []))
    if sum(action.get('estimatedSeconds', 0) for action in actions) > minutes * 60:
        raise E('当前动作与组间休息超出计划时长。请调整动作或延长时段。')
    ctx['plan'].update(title=title,date=day,time=clock,minutes=minutes,
                       version=ctx['plan']['version']+1,source='用户确认 · 本地计划',updatedAt=stamp())
    ctx['plan'].update(action_patch)
    for key, limit in (('purpose',120),('content',1500),('equipment',200)):
        if key in body:
            ctx['plan'][key]=string(body,key,limit)
        else:
            ctx['plan'].setdefault(key,'')
    if actions and training.enabled():
        catalog = training.exercises_by_id()
        equipment = sorted({item for action in actions for item in catalog.get(action['exerciseId'], {}).get('equipment', [])})
        ctx['plan']['equipment'] = '、'.join(equipment) if equipment else '徒手'
    ctx['contextVersion']+=1


def edit_alternatives(ctx,body):
    E,_,string,integer,_,_=helpers()
    items=body.get('items')
    if not isinstance(items,list) or len(items)>8:
        raise E('最多可保存 8 个已确认的备选方案。')
    values=[]
    previous={item['id']:item for item in ctx.get('alternatives',[])}
    for item in items:
        if not isinstance(item,dict):
            raise E('备选方案格式不正确。')
        ident=string(item,'id',60) or uuid.uuid4().hex
        if ident=='reschedule' or any(x['id']==ident for x in values):
            raise E('备选编号重复或被保留。')
        value={'id':ident,'title':string(item,'title',100,True),'minutes':integer(item.get('minutes'),1,240),
               'source':'用户确认 · 自有备选方案'}
        for key, limit in (('purpose',120),('content',1500),('equipment',200)):
            value[key]=string(item,key,limit) if key in item else previous.get(ident,{}).get(key,'')
        intensity=string(item,'intensity',20) if 'intensity' in item else previous.get(ident,{}).get('intensity','routine')
        if intensity not in ('routine','light','any'):
            raise E('请选择常规、低负荷或其他训练强度。')
        value['intensity']=intensity
        values.append(value)
    ctx['alternatives']=values
    ctx['contextVersion']+=1


def get_record(db,table,ident):
    E,_,_,_,_,_=helpers()
    if table not in ('sessions','video_jobs','tasks'):
        raise ValueError('table')
    row=db.execute(f'SELECT data FROM {table} WHERE id=?',(ident,)).fetchone()
    if not row:
        raise E('记录不存在或已删除。','not_found',404)
    return json.loads(row[0])


def save_session(db,ctx,body,update=False,*,workout=None):
    E,stamp,string,integer,boolean,encode=helpers()
    old=None
    if update:
        old=get_record(db,'sessions',string(body,'id',64,True))
        if integer(body.get('expectedRevision'),1,2**31-1)!=old['revision']:
            raise E('训练记录已更新，请刷新后修改。','stale_session',409)
        for key in ('taskId','videoJobId'):
            if key in body and body[key]!=old.get(key):
                raise E('不能改变训练记录关联的任务或视频。')
    task_id=old.get('taskId') if old else (string(body,'taskId',64) or None)
    job_id=old.get('videoJobId') if old else (string(body,'videoJobId',64) or None)
    task=None
    if task_id:
        task=get_record(db,'tasks',task_id)
        if task['status'] not in ('saved','partial'):
            raise E('关联的计划尚未确认。','plan_not_saved',409)
    completion=string(body,'completion',20,True)
    if completion not in ('completed','partial','not_done'):
        raise E('请选择有效的完成状态。')
    exercise_entries = training.session_entries(body, old, completion)
    minutes=integer(body.get('minutes'),0,240)
    if (completion=='not_done' and minutes!=0) or (completion!='not_done' and minutes==0):
        raise E('未训练请填写 0 分钟；已训练请填写实际时长。')
    feeling=string(body,'feeling',10,True)
    if feeling not in ('合适','偏累','偏轻松','不合适'):
        raise E('请选择训练感受。')
    day=string(body,'performedAt',10) or str(date.today())
    try:
        if str(date.fromisoformat(day))!=day or date.fromisoformat(day)>date.today():
            raise ValueError
    except ValueError:
        raise E('请填写有效的训练日期，不支持未来日期。')
    observation=old.get('observation') if old else None
    if job_id and not old:
        job=get_record(db,'video_jobs',job_id)
        if job['status']!='done':
            raise E('视频尚未完成分析。','video_not_ready',409)
        result=job['result']
        observation={k:result.get(k) for k in ('quality','validRatio','side','sourceUrl','modelVersion','ruleVersion','cycleDurationSeconds','exercise','exerciseName')}
        observation.update(originalCount=result.get('count'),confirmedCount=result.get('count'),correctionReason='')
    if observation:
        observation=dict(observation)
        count=body.get('correctedCount',observation['confirmedCount'])
        if count is not None:
            count=integer(count,0,1000)
        reason=string(body,'correctionReason',200) if 'correctionReason' in body else observation.get('correctionReason','')
        if count!=observation['originalCount'] and not reason:
            raise E('请填写次数校正的原因。','correction_reason_required')
        observation.update(confirmedCount=count,correctionReason=reason)
    elif 'correctedCount' in body and body['correctedCount'] is not None:
        raise E('请先关联一段已分析的视频再校正次数。')
    at=stamp()
    weight=body.get('weight',(old or {}).get('weight',0))
    try:
        if isinstance(weight,bool):
            raise ValueError()
        weight=float(weight)
    except (TypeError,ValueError,OverflowError):
        raise E('请填写有效重量，范围为 0–500 kg。')
    if not math.isfinite(weight) or not 0<=weight<=500:
        raise E('重量需要在 0–500 kg 范围内。')
    sample_plan='示例' in ctx['plan'].get('source','') and not ctx.get('profileConfirmed')
    example=(is_example_session(old) if old
             else task.get('example','示例' in task['original'].get('source','')) if task else sample_plan)
    record={'id':old['id'] if old else uuid.uuid4().hex,'revision':old['revision']+1 if old else 1,
            'createdAt':old['createdAt'] if old else at,'updatedAt':at,'performedAt':day,'taskId':task_id,'videoJobId':job_id,
            'completion':completion,'minutes':minutes,'feeling':feeling,'discomfort':boolean(body.get('discomfort')),
            'note':string(body,'note',500),'observation':observation,'example':bool(example),
            'exercise':string(body,'exercise',40) or (observation or {}).get('exercise') or (old or {}).get('exercise','general'),
            'exerciseName':string(body,'exerciseName',60) or (observation or {}).get('exerciseName') or (old or {}).get('exerciseName','自主训练'),
            'sets':integer(body.get('sets',(old or {}).get('sets',1)),1,20),
            'reps':integer(body.get('reps',(old or {}).get('reps',0)),0,1000),
            'weight':weight}
    if exercise_entries is not None:
        record['exerciseEntries'] = exercise_entries
        if exercise_entries and not observation:
            record['exercise'] = exercise_entries[0]['exerciseId'] if len(exercise_entries) == 1 else 'general'
            record['exerciseName'] = exercise_entries[0]['exerciseName'] if len(exercise_entries) == 1 else f'动作训练 · {len(exercise_entries)} 项'
    if workout:
        record.update(workoutId=workout['id'], workoutTitle=workout['title'],
                      workoutPlanVersion=workout['planVersion'], workoutActions=workout['actions'])
    elif old and 'workoutId' in old:
        record.update({key: old[key] for key in ('workoutId', 'workoutTitle', 'workoutPlanVersion', 'workoutActions')})
    record['example'] = is_example_session(record)
    db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)',(record['id'],encode(record)))
    refresh_context(db,ctx)
    analytics.record(db,'training_recorded',{'sessionId':record['id'],'completion':record['completion'],'revision':record['revision']})
    if record.get('observation'):
        observation=record['observation']
        changed=observation['confirmedCount']!=observation['originalCount']
        analytics.record(db,'observation_confirmed',{'sessionId':record['id'],'jobId':record['videoJobId'],
            'revision':record['revision'],'corrected':changed,
            'reasonCode':'user_corrected' if changed else 'unchanged'})
    return record['id']
