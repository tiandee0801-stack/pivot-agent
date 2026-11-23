"""A complete, explicitly labelled scenario for untouched visitor workspaces."""
import json
from datetime import date, timedelta

def initialize(connection):
    row=connection.execute('SELECT data FROM workspace WHERE id=1').fetchone()
    ctx=json.loads(row[0])
    if ctx.get('experience') or not ctx.get('pristine') or ctx.get('profileConfirmed'):
        return
    if connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] or connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]:
        return
    day=date.today()
    saturday=day+timedelta(days=(5-day.weekday())%7 or 7)
    ctx['experience']={'version':2,'createdDate':str(day),'eventDate':str(saturday),
        'label':'示例计划','metrics':[{'label':'睡眠','value':'6.5','unit':'小时'},
        {'label':'静息心率','value':'58','unit':'bpm'}, {'label':'HRV · SDNN','value':'45','unit':'ms'}]}
    ctx['plan'].update(title='全身力量 · 篮球配套',purpose='保持力量训练节奏，兼顾周末篮球',
        content='热身 10 分钟；上肢推拉 20 分钟；下肢力量 20 分钟；整理 10 分钟。沿用原计划负荷。',
        equipment='健身房、哑铃',source='示例计划')
    ctx['profile'].update(goal='兼顾力量与篮球，忙碌时也保持运动习惯',preferredTime='18:30')
    ctx['goalContext']={'eventName':'周末篮球','eventDate':str(saturday),'endDate':str(day+timedelta(days=14))}
    source='示例备选 · 剧本中已确认'
    ctx['alternatives']=[
        {'id':'short','title':'哑铃力量 · 30 分钟','minutes':30,'source':source,
         'purpose':'保留上肢力量训练，周末球局不变','content':'热身 5 分钟；原计划上肢推拉 20 分钟；整理 5 分钟。本次不包含下肢力量部分，后续另行安排。',
         'equipment':'哑铃','equipmentRequired':['哑铃'],'intensity':'routine','goalTags':['上肢'],
         'retained':'保留原计划的上肢力量训练。','changed':'按已有哑铃短版压缩至 30 分钟，省略原计划的下肢部分。'},
        {'id':'band','title':'弹力带力量 · 30 分钟','minutes':30,'source':source,
         'purpose':'保留上肢力量训练，适配只有弹力带的训练条件','content':'热身 5 分钟；沿用已有的弹力带上肢推拉备选 20 分钟；整理 5 分钟。',
         'equipment':'弹力带','equipmentRequired':['弹力带'],'intensity':'routine','goalTags':['上肢'],
         'retained':'保留原计划的上肢力量训练目的。','changed':'用已确认的弹力带短版代替哑铃内容，省略原计划的下肢部分。'},
        {'id':'routine_20','title':'徒手力量 · 20 分钟','minutes':20,'source':source,
         'purpose':'保留力量训练习惯','content':'沿用已有的 20 分钟徒手力量备选，包含热身和整理。',
         'equipment':'徒手','equipmentRequired':[],'intensity':'routine','goalTags':['全身'],
         'retained':'保留力量训练习惯。','changed':'改用原有徒手短版，省略器械模块。'},
        {'id':'light','title':'轻量活动 · 15 分钟','minutes':15,'source':source,
         'purpose':'维持活动习惯，本次不做力量训练','content':'沿用已有的 15 分钟轻量活动备选，不增加重量或额外训练量。',
         'equipment':'徒手','equipmentRequired':[],'intensity':'light',
         'retained':'保留活动习惯和近期球局。','changed':'本次改为已有的低负荷备选，力量训练另行安排。'}]
    connection.execute('UPDATE workspace SET data=? WHERE id=1',(json.dumps(ctx,ensure_ascii=False),))
