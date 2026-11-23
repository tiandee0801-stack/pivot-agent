"""Local, single-profile Pivot simulation. Only a confirmed draft changes the plan."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
import mobile_records as mobile
import analytics
import training_catalog as training
import workout
import time as monotonic_time
from datetime import date, datetime, time, timedelta


DEVICE_MODES = {"complete", "missing", "stale", "disconnected"}
OPEN_STATES = {"needs_info", "draft"}
PROFILE_FIELDS = {"goal", "sport", "preferredTime", "constraint"}
KINDS = {"shorten", "reschedule", "fatigue", "maintain"}
ALT_PLANS = [
    {"id": "short", "title": "力量训练 · 精简版", "minutes": 30, "source": "示例备选 · 请按自身已有方案编辑", "intensity": "routine"},
    {"id": "light", "title": "轻量活动", "minutes": 15, "source": "示例备选 · 请按自身已有方案编辑", "intensity": "light", "equipmentRequired": []},
]
SYMPTOMS = r"疼痛|不适|不舒服|不舒适|受伤|肿胀|肿痛|发烧|发热|胸闷|气短|气喘|心慌|心悸|眩晕|头晕|头昏|恶心|喘不过气|呼吸困难|刺痛|难受|疼|痛|扭伤|崴脚|肿"
NEG = r"(?:没有|并无|未出现|无|没|不再|不)(?:任何|什么|明显的?|其他|感到|觉得|再)?"
STATES = {"complete": "同步完整", "missing": "部分记录缺失", "stale": "数据已过期", "disconnected": "设备未连接"}


class RequestError(Exception):
    def __init__(self, message, code="invalid_input", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today():
    return datetime.now().astimezone().date()


def seeded():
    day = today()
    return {
        "plan": {"id": uuid.uuid4().hex, "title": "力量训练", "date": str(day), "time": "18:30",
                 "minutes": 60, "version": 1, "source": "示例计划 · 请先确认或编辑"},
        "profile": {"goal": "维持规律训练", "sport": "力量训练、篮球", "preferredTime": "傍晚", "constraint": ""},
        "permissions": {"device": False, "save": True, "reminder": False},
        "profileAt": stamp(), "profileConfirmed": False, "contextVersion": 1, "deviceMode": "disconnected", "sampleDay": str(day),
        "activity": {"title": "篮球", "date": str(day - timedelta(days=1)), "minutes": 45, "source": "用户手记 · 模拟记录"},
        # Internal diary windows and a conflicting meeting. External calendars are never queried.
        "windows": [{"date": str(day + timedelta(days=n)), "start": "18:30", "end": "20:30"} for n in (1, 2)],
        "busy": [{"date": str(day + timedelta(days=1)), "start": "19:45", "end": "20:30"}],
        "active": None, "pristine": True,
    }


def encode(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def bootstrap(db):
    analytics.initialize(db)
    analytics.initialize_interpretations(db)
    db.execute("CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    row = db.execute("SELECT data FROM workspace WHERE id=1").fetchone()
    if row:
        ctx = json.loads(row[0])
        mobile.initialize(db, ctx)
        return ctx
    ctx = seeded()
    mobile.initialize(db, ctx)
    db.execute("INSERT INTO workspace VALUES(1,?)", (encode(ctx),))
    return ctx


def string(data, key, maxlen=200, required=False):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > maxlen:
        raise RequestError(f"文字格式有误，最多可填写 {maxlen} 个字。")
    if required and not value.strip():
        raise RequestError("请先输入内容。")
    return value.strip()


def boolean(value):
    if type(value) is not bool:
        raise RequestError("开关状态无效，请重试。")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RequestError(f"请输入 {low} 到 {high} 的整数。")
    return value


def device(ctx):
    if ctx.get("wearable") or ctx.get("realDeviceOnly"):
        from wearable import device_view
        return device_view(ctx)
    day = date.fromisoformat(ctx["sampleDay"])
    mode = ctx["deviceMode"]
    if day != today() and mode == "complete":
        mode = "stale"
    permitted = ctx["permissions"]["device"]
    description = {
        "complete": "示例记录完整。个人基线样本不足，不能推算恢复程度。",
        "missing": "本次模拟同步仅收到静息心率，睡眠和 HRV 缺失。",
        "stale": "记录超出当天使用范围，仅供回看。",
        "disconnected": "模拟手环已断开，本次任务无法读取记录。",
    }
    device_day = day - timedelta(days=3) if ctx["deviceMode"] == "stale" else day
    at = f"{device_day} 07:10"
    metrics = [
        {"label":"睡眠时长","value":"6 小时 40","unit":"分","source":"模拟手环 · 昨夜睡眠","at":at},
        {"label":"静息心率","value":"58","unit":"次/分","source":"模拟手环 · 夜间静息摘要","at":at},
        {"label":"HRV","value":"48","unit":"ms","source":"模拟手环 · 清晨 5 分钟 RMSSD","at":at},
    ]
    if mode == "missing":
        metrics = metrics[1:2]
    if not permitted or mode == "disconnected":
        metrics = []
    return {"mode": mode, "label": STATES[mode] if permitted else "未授权读取",
            "syncedAt": at if permitted and mode != "disconnected" else "",
            "quality": description[mode] if permitted else "开启设备读取授权后，可将模拟记录用于本次调整。",
            "metrics": metrics, "simulated": True}


def facts(ctx, task):
    p = task["original"]
    evidence = [{"label":"原安排","value":f"{p['title']} · {p['minutes']} 分钟","at":p["date"]+" "+p["time"],
                 "source":p["source"]}]
    for key,label in (("goal","当前目标"),("constraint","已确认约束"),("preferredTime","偏好时段")):
        if key=='goal' and ctx.get('goalContext',{}).get('endDate') and ctx['goalContext']['endDate']<str(today()):
            evidence.append({'label':'阶段目标已到期','value':'需要本人重新确认，当前仅保留历史。','source':'目标到期规则','at':ctx['goalContext']['endDate']})
            continue
        if ctx["profile"][key]:
            evidence.append({"label":label, "value":ctx["profile"][key], "source":"已确认的个人档案" if ctx.get("profileConfirmed") else "示例档案 · 未确认","at":ctx["profileAt"]})
    gc=known_ball_game(ctx, task)
    if gc.get('eventName') and gc.get('eventDate','')>=str(today()):
        evidence.append({'label':'近期重要运动','value':gc['eventName']+' · '+gc['eventDate'],'source':'用户确认的活动安排' if ctx.get('profileConfirmed') else '示例活动安排','at':ctx['profileAt']})
    if p.get('content'):
        evidence.append({'label':'原训练内容','value':p['content'],'source':p['source'],'at':p['date']})
    act = ctx["activity"]
    if "模拟" not in act.get("source", "") and "示例" not in act.get("source", ""):
        evidence.append({"label":"最近运动","value":f"{act['title']} · {act['minutes']} 分钟","source":act["source"],"at":act["date"]})
    for record in recent_sessions(ctx, task)[:3]:
        status = {"completed":"已完成", "partial":"部分完成", "not_done":"未训练"}[record["completion"]]
        basketball = record.get('exercise') == 'basketball'
        name = '篮球' if basketball else record.get('workoutTitle') or record.get('exerciseName') or '训练'
        detail = f"{'篮球' if basketball else status} · {record['minutes']} 分钟 · {record['feeling']}"
        observation = record.get("observation")
        if observation:
            count = observation.get("confirmedCount")
            detail += f" · {observation.get('exerciseName','动作')} {count} 次（用户确认）" if count is not None else " · 视频次数无法确认"
        if record.get("discomfort"):
            detail += " · 用户报告不适（历史反馈，需确认当日状态）"
        evidence.append({"label":"篮球记录" if basketball else "实际训练反馈", "value":detail,
                         "source":"示例训练记录" if mobile.is_example_session(record) else "用户训练记录",
                         "at":record["performedAt"], "sessionId":record["id"], "revision":record["revision"],
                         "exercise":record.get('exercise', 'general'), "exerciseName":name, "minutes":record['minutes'],
                         "completion":record['completion'], "feeling":record['feeling']})
    d = device(ctx)
    unknowns = ["个人基线不足，手环数据不能确定今天的身体状态。"]
    if ctx["permissions"]["device"] and d["mode"] in ("complete","missing"):
        for m in d.get('evidenceMetrics', d["metrics"]):
            evidence.append({"label":m["label"],"value":m["value"]+" "+m["unit"],"at":m["at"],"source":m["source"],"device":True})
    if not ctx["permissions"]["device"] or d["mode"] != "complete":
        unknowns.append(d["quality"])
    if task["minutes"] is not None:
        evidence.append({"label":"可用时间","value":f"{task['minutes']} 分钟","source":"本次输入","at":task["updatedAt"]})
    if task["feeling"]:
        evidence.append({"label":"当日自述","value":task["feeling"],"source":"本次输入","at":task["updatedAt"]})
    if task.get("sleepChanged"):
        evidence.append({"label":"睡眠变化","value":"昨晚睡眠有变化，需结合当日自述。","source":"本次输入","at":task["updatedAt"]})
    if task.get("availableEquipment"):
        evidence.append({"label":"当次器械","value":task["availableEquipment"],"source":"本次输入","at":task["updatedAt"]})
    if task.get("restriction"):
        evidence.append({"label":"当次限制","value":task["restriction"],"source":"本次输入","at":task["updatedAt"]})
    if not task["feeling"]:
        unknowns.append("今天的主观感受还未确认。")
    return evidence, unknowns


def transition(task, status):
    task["updatedAt"] = stamp()
    task["status"] = status
    task["timeline"].append({"status":status,"at":task["updatedAt"],"draftVersion":task["draftVersion"]})


def clock_minutes(clock):
    h, m = map(int, clock.split(":"))
    return h * 60 + m


def free_slot(ctx, day, clock, minutes):
    start = clock_minutes(clock)
    end = start + minutes
    in_window = any(w["date"] == day and clock_minutes(w["start"]) <= start and end <= clock_minutes(w["end"])
                    for w in ctx["windows"])
    occupied = any(b["date"] == day and start < clock_minutes(b["end"]) and clock_minutes(b["start"]) < end
                   for b in ctx["busy"])
    return day >= str(today()) and in_window and not occupied


NUMBER = r"[+-]?\d+(?:\.\d+)?|[零一二两三四五六七八九十百]+"
DURATION = re.compile(
    rf"(?:(?P<hours>{NUMBER})\s*(?:个)?(?P<half>半)?\s*(?:小时|钟头|hours?\b|h\b)"
    rf"(?:\s*(?P<extra>{NUMBER})\s*分钟|(?P<posthalf>半))?"
    rf"|半(?:个)?(?:小时|钟头)"
    rf"|(?P<quarter>[一二两三])刻(?:钟)?"
    rf"|(?P<minutes>{NUMBER})\s*(?:分钟|min(?:utes?)?\b|分(?=[，。\s]|$)))",
    re.IGNORECASE,
)
UNAVAILABLE_TIME = re.compile(r"原(?:来|定|本|计划)|平时|之前|上次|昨天|昨晚|开会|打(?:过)?球|篮球|通勤|已(?:练|用)|不能(?:再)?练")
AVAILABLE_TIME = re.compile(r"只(?:有|剩|能)|最多|可用|空(?:出|闲)|抽出|压缩到|缩短到|改成|但(?:是)?|能练|腾出")


def number_value(raw):
    try:
        return float(raw)
    except ValueError:
        digits = dict(zip("零一二三四五六七八九", range(10)))
        digits["两"] = 2
        total = digit = 0
        for char in raw:
            if char in "十百":
                total += (digit or 1) * (10 if char == "十" else 100)
                digit = 0
            else:
                digit = digits[char]
        return total + digit


def parse_minutes(s):
    # Prefer the time the user actually has; an existing plan or past activity also has a duration.
    candidates = []
    for clause in re.split(r"[，,。；;！!？?\n]", s):
        previous_end = 0
        for m in DURATION.finditer(clause):
            context = clause[previous_end:m.start()]
            previous_end = m.end()
            priority = 2 if AVAILABLE_TIME.search(context) else 1
            if priority == 1 and UNAVAILABLE_TIME.search(context):
                continue
            if m["hours"]:
                mins = 60 * number_value(m["hours"]) + number_value(m["extra"] or "0")
                if m["half"] or m["posthalf"]:
                    mins += 30
            elif m["minutes"]:
                mins = number_value(m["minutes"])
            elif m["quarter"]:
                mins = 15 * number_value(m["quarter"])
            else:
                mins = 30
            candidates.append((priority, mins))
    if not candidates:
        return None
    rank = max(p for p, _ in candidates)
    values = {mins for p, mins in candidates if p == rank}
    if len(values) != 1:
        return None
    mins = values.pop()
    if 0 <= mins <= 1440 and mins != int(mins):
        raise RequestError("请用整分钟描述这次可用的时间。")
    if not 0 <= mins <= 1440:
        raise RequestError("请填写 0 到 1440 分钟之间的可用时长。")
    return int(mins)


def safety(s):
    # Remove explicit negations only. A symptom after a contrasting clause still triggers a stop.
    normalized = re.sub(r"(?:并非|不是|不能说|谈不上|不能算)(?:没有|无|不|没)", "有", s)
    symptom = "(?:" + SYMPTOMS + ")"
    # The negation scopes over a connected symptom list, but never crosses a
    # contrasting clause (e.g. 没有疼痛或不适，但胸闷).
    connected = r"(?:(?:或|和|及|与|、|以及)?(?:明显的?|其他)?" + symptom + ")*"
    remaining = re.sub(NEG + symptom + connected, "", normalized)
    return bool(re.search(SYMPTOMS + r"|医生.{0,6}(?:禁止|不让|要求暂停).{0,4}(?:运动|训练)", remaining))


DAY_WORD = re.compile(
    r"大后天|后天|明天|明晚|明早|明日|今天|今日|今晚|今早|"
    r"(?:下周|下星期|这周|本周|周|星期)[一二三四五六日天]|"
    r"\d{4}-\d{1,2}-\d{1,2}|(?:\d{4}年)?\d{1,2}月\d{1,2}[号日]?"
)
CLOCK_WORD = re.compile(
    rf"(?P<period>凌晨|早上|早晨|上午|中午|下午|晚上|晚间)?\s*"
    rf"(?P<hour>{NUMBER})(?:(?:[:：])(?P<minute>\d{{2}})|[点时](?:(?P<half>半)|(?P<mins>{NUMBER})分)?)"
)
NEGATIVE_SLOT = re.compile(r"没(?:有)?(?:时间|空)|有事|有约|加班|不(?:方便|行|想|能|可以)|占用|要开会|排满")
PERIOD_HOURS = {"凌晨":(0,6),"早上":(5,10),"早晨":(5,10),"上午":(6,12),"中午":(11,14),
                "下午":(12,18),"晚上":(18,24),"晚间":(18,24)}


def decode_day(word):
    base = today()
    offsets = {"大后天":3, "后天":2, "明天":1,"明晚":1,"明早":1,"明日":1,"今天":0,"今日":0,"今晚":0,"今早":0}
    if word in offsets:
        return str(base + timedelta(days=offsets[word]))
    nums = [int(x) for x in re.findall(r"\d+", word)]
    if nums:
        try:
            return str(date(*(nums if len(nums)==3 else [base.year]+nums)))
        except ValueError:
            return None
    weekday = "一二三四五六日".index(word[-1].replace("天","日"))
    delta = weekday-base.weekday()
    if word.startswith("下"):
        delta += 7
    elif not word.startswith(("本", "这")):
        delta %= 7
    return str(base+timedelta(days=delta))


def calendar_request(t, s):
    """Resolve only expressible calendar choices. Never silently replace the requested slot."""
    schedule_context = t["move"] is True or t["kind"]=="reschedule" or re.search(r"改到|改期|挪|推迟|换到|另约|换个时间|提前到|改在|改成",s)
    if not schedule_context:
        return
    selected_days, selected_times, periods = set(), set(), set()
    denied = set(t.get("excludedDates", []))
    unclear = False
    for clause in re.split(r"[，,；;。！？!?\n]|但(?:是)?",s):
        if re.search(r'球局|打球|约球|球赛',clause) and not re.search(r'改到|改在|挪到|换到|力量训练.{0,5}(?:在|到)',clause):
            continue
        words = DAY_WORD.findall(clause)
        if re.search(r"下个月|下下周|下礼拜|下周末|周末|周[一二三四五六日]至|月底|工作日|节后|下周(?![一二三四五六日天])|(?:\d+)天(?:后|以后)",clause):
            unclear = True
        if not words and not CLOCK_WORD.search(clause) and not any(p in clause for p in PERIOD_HOURS):
            continue
        # A mention of today's shortage is context, not a request to schedule today.
        for word in words:
            d=decode_day(word)
            if not d:
                unclear=True
                continue
            if NEGATIVE_SLOT.search(clause) and not re.search(r"改到|改在|挪到|换到",clause):
                denied.add(d)
            elif word not in ("今天","今日","今晚","今早") or re.search(r"(?:改到|改在|挪到|换到|想在)(?:今天|今日|今晚|今早)",clause):
                selected_days.add(d)
            if word in ("明晚","今晚"):
                periods.add("晚上")
            elif word in ("明早","今早"):
                periods.add("早上")
        if NEGATIVE_SLOT.search(clause) and words and not re.search(r"改到|改在|挪到|换到",clause):
            continue
        c = CLOCK_WORD.search(clause)
        if c:
            hr=number_value(c["hour"])
            minute=30 if c["half"] else number_value(c["minute"] or c["mins"] or "0")
            period=c["period"]
            if not period and any(w in ("明晚","今晚") for w in words):
                period="晚上"
            if period in ("中午","下午","晚上","晚间") and 1 <= hr < 12:
                hr+=12
            if not 0<=hr<24 or not 0<=minute<60 or hr!=int(hr) or minute!=int(minute) or re.search(r"以前|以后|之前|之后|左右|到.*[点时]|或.*[点时]",clause[c.end():]):
                unclear=True
            else:
                selected_times.add(f"{int(hr):02}:{int(minute):02}")
        else:
            periods.update(p for p in PERIOD_HOURS if p in clause)
    if selected_days or selected_times or periods or unclear:
        t["calendarUnclear"]=unclear or any(len(x)>1 for x in (selected_days,selected_times,periods))
        if len(selected_days)==1:
            t["requestedDate"]=selected_days.pop()
        if len(selected_times)==1:
            t["requestedTime"]=selected_times.pop()
            t["requestedPeriod"]=None
        elif len(periods)==1:
            t["requestedPeriod"]=periods.pop()
            t["requestedTime"]=None
        t["move"]=True
        t["kind"]="reschedule"
    t["excludedDates"]=sorted(denied)


EQUIPMENT_ALIASES = {
    '哑铃': ('哑铃',), '弹力带': ('弹力带', '阻力带', '弹力圈'), '杠铃': ('杠铃',),
    '壶铃': ('壶铃',), '单杠': ('单杠', '引体杠'), '双杠': ('双杠',),
    '拉力器': ('拉力器', '拉力绳', '滑轮', '龙门架'), '训练凳': ('训练凳', '哑铃凳', '卧推凳'),
    '垫': ('训练垫', '瑜伽垫'), '跳绳': ('跳绳',), '跑步机': ('跑步机',),
    '固定器械': ('固定器械', '腿举机', '史密斯机'), '泡沫轴': ('泡沫轴',), '球': ('篮球', '足球', '排球'),
}
NO_EQUIPMENT = re.compile(r"徒手|自重|无器械|不用器械|不需要器械|没有器械|没器械|无需器械")
FOCUS = {'上肢', '下肢', '核心', '爆发', '平衡', '耐力', '速度', '柔韧'}
RESTRICTION = re.compile(r'(?:明确)?(?:不(?:要|能|可|做|练|安排|使用|用)|避免|禁止)(?:再|做|练|安排|使用|用)?\s*([^，,。；;！!？?\n]{1,35})')
BALL_CHANGE = re.compile(r'临时.{0,5}(?:约|打|有).{0,5}球|临时.{0,5}球局|(?:打球|球局|球赛).{0,6}(?:冲突|撞)|(?:改期|调整).{0,6}(?:打球|球局)')
SLEEP_CHANGE = re.compile(r'睡眠不足|睡不够|没睡好|睡眠不好|睡得不好|睡得少|睡眠变化|睡得差')
NORMAL = re.compile(NEG + '(?:'+SYMPTOMS+')' + r'|(?:状态|感觉)(?:还好|很好|正常|良好|不错)|不累|精神不错')
TIRED = re.compile(r'疲劳|疲惫|偏累|累了|(?:有点|有些|感觉|很|太)累|没精神')


def equipment_tokens(text):
    """Use known aliases and preserve explicitly written custom equipment names."""
    tags=set()
    for part in re.split(r'[、，,；;和与及+＋]',text or ''):
        part=part.strip()
        if part and part not in ('健身房','已有轻量活动场地','未知') and not NO_EQUIPMENT.fullmatch(part):
            known={name for name, aliases in EQUIPMENT_ALIASES.items() if any(word in part for word in aliases)}
            tags.update(known or {part})
    return tags


def recent_sessions(ctx, task):
    records = (r for r in ctx.get('recentSessions', []) if r.get('performedAt', '') <= str(today())
               and mobile.is_example_session(r) == bool(task.get('example')))
    return sorted(records, key=lambda r:(r['performedAt'],r.get('createdAt',''),r.get('revision',0)), reverse=True)


def current_clauses(text):
    return [clause for clause in re.split(r'[，,。；;！!？?\n]|但(?:是)?',text)
            if (not re.search(r'昨晚|昨天|上次|此前|之前|上周|练后',clause)
                or re.search(r'今天|今日|当前|现在|目前|当下',clause))
            and not re.match(r'\s*(如果|假如|假设)',clause)]


def note_input(task, s, intent, interpretation):
    if interpretation is not None:
        task["interpretation"] = interpretation
    classified = isinstance(intent,dict) and intent.get("kind") in KINDS | {"other"}
    if classified:
        task["mode"] = "model"
    clauses = current_clauses(s)
    current = '，'.join(clauses)
    if safety(current) or (classified and intent.get("discomfort") is True and current == s and not NORMAL.search(current)):
        task["feeling"] = "报告了不适"
        return
    if task['original'].get('actions'):
        note_training_conditions(task, clauses)
    minutes = parse_minutes(s)
    if minutes is not None:
        task["minutes"] = minutes
        task["kind"] = "shorten"
    if NORMAL.search(current):
        task["feeling"] = "未报告明显不适"
    if TIRED.search(re.sub(r'(?:没有|没|不|无)(?:明显)?(?:疲劳|疲惫|偏累)','',current)):
        task["feeling"] = "今天有些疲劳"
        if not task['kind']:
            task['kind'] = 'fatigue'
    if SLEEP_CHANGE.search(s):
        task['sleepChanged'] = True
    if not task['kind'] and task.get('sleepChanged'):
        task["kind"] = "fatigue"
    if re.search(r"维持|保持状态|保状态|保持运动习惯|保持习惯", current):
        task["kind"] = "maintain"
    if re.search(r"不(?:想|用|愿意|能)?(?:改期|挪到|推迟)|今天练|今天完成|不换日", s):
        task["move"] = False
        if task['kind'] == 'reschedule' and task['original'].get('actions'):
            task['kind'] = 'shorten'
        if task['original'].get('actions'):
            task["explicitMove"] = False
        for key in ("requestedDate", "requestedTime", "requestedPeriod", "calendarUnclear"):
            task.pop(key, None)
    elif re.search(r"改期|换一天|推迟|挪到|明天练|明天训练|另一天|改到|改天", s) or BALL_CHANGE.search(s):
        task["move"] = True
        task["kind"] = "reschedule"
        if task['original'].get('actions') and re.search(r"改期|换一天|推迟|挪到|明天练|明天训练|另一天|改到|改天", s):
            task["explicitMove"] = True
    if not task["kind"] and re.search(r"缩短|精简|少练|压缩|时间不够|来不及|时间变少", s):
        task["kind"] = "shorten"
    if not task["kind"] and re.search(r"打球|篮球|羽毛球|球局", s):
        task["kind"] = "reschedule"
    if not task["kind"] and classified and intent["kind"] in KINDS:
        task["kind"] = intent["kind"]
    if task.get('move') is not False:
        calendar_request(task, s)
    for clause in clauses:
        equipment_hint = re.search(r'(?:只有|仅有|只能用|可用器械(?:有|是|为)?|能用|器械是)\s*([^，,。；;！!？?\n]{1,40})',clause)
        available = equipment_hint[1] if equipment_hint else clause.strip()
        named = equipment_tokens(available) & EQUIPMENT_ALIASES.keys()
        bare_equipment = any(available in aliases for aliases in EQUIPMENT_ALIASES.values())
        if re.search(r'器械.{0,4}(?:未知|不清楚|不知道)|(?:不清楚|不知道)可用器械',clause):
            task['availableEquipment'] = '未知'
        elif NO_EQUIPMENT.search(available):
            task['availableEquipment'] = '徒手'
        elif named and (equipment_hint or bare_equipment or re.search(r'有(?:个|一副|一对)?(?:哑铃|弹力带|阻力带|杠铃|壶铃)',clause)) and not re.search(r'没有|没带|不能用|不用|禁止',clause):
            task['availableEquipment'] = '、'.join(sorted(named))
        elif named and re.search(r'没有|没带|不能用|不用|禁止',clause):
            terms = '、'.join(sorted(named))
            task['restriction'] = (task.get('restriction','')+'、'+terms).strip('、')
        restricted = RESTRICTION.search(clause)
        if restricted and not NORMAL.search(clause) and not re.search(r'改期|挪到|推迟|再练\d|器械',restricted[1]):
            task['restriction'] = (task.get('restriction','')+'、'+restricted[1]).strip('、')


def note_training_conditions(task, clauses):
    spaces = {'home': r'家里|居家|在家', 'gym': r'健身房|力量房', 'court': r'球场|球馆'}
    for clause in clauses:
        if BALL_CHANGE.search(clause) and re.search(r'今晚|今天|今日|今早|中午|下午', clause):
            task['sameDayBall'] = True
        places = [space for space, words in spaces.items() if re.search(words, clause)]
        if len(places) == 1 and not re.search(r'不在|不去|不是|不方便|没有', clause):
            task['space'] = places[0]
        if '固定点' not in clause:
            continue
        if re.search(r'没有|没找到|无(?:合适|安全|可靠)?固定点|无法|不能|不确定|不安全|不牢靠', clause):
            task['anchorAvailable'] = False
        elif re.fullmatch(r'(?:确认|我确认)?(?:有|已有|具备)(?:一个)?(?:合适的|安全的|可靠的|牢固的)?(?:弹力带)?固定点', clause.strip()):
            task['anchorAvailable'] = True
        elif re.fullmatch(r'(?:弹力带)?固定点(?:已经|已)确认(?:安全|合适|牢固)?', clause.strip()):
            task['anchorAvailable'] = True


def note_context(task, body):
    data = body.get('context')
    if data is None:
        return
    if not isinstance(data,dict):
        raise RequestError('请检查当次调整条件。')
    scenario = string(data,'scenario',10)
    if scenario:
        kinds = {'short':'shorten','tired':'fatigue','ball':'reschedule'}
        if scenario not in kinds:
            raise RequestError('未知的调整场景。')
        task.update(kind=kinds[scenario],move=scenario=='ball')
    if 'sleepChanged' in data:
        task['sleepChanged']=boolean(data['sleepChanged'])
    if 'anchorAvailable' in data:
        task['anchorAvailable'] = boolean(data['anchorAvailable'])
    if 'space' in data:
        space = string(data, 'space', 10)
        if space not in training.SPACES:
            raise RequestError('请选择居家、健身房或球场。')
        task['space'] = space
    if 'minutes' in data and data['minutes'] is not None:
        task['minutes']=integer(data['minutes'],0,1440)
    for field,key,limit in (('equipment','availableEquipment',200),('restriction','restriction',200)):
        if field in data:
            value=string(data,field,limit)
            if value:
                task[key]=value
    condition = string(data,'condition',10)
    if condition:
        feelings = {'unknown':'','normal':'未报告明显不适','tired':'今天有些疲劳','pain':'报告了不适'}
        if condition not in feelings:
            raise RequestError('未知的身体感受。')
        if task.get('feeling') != '报告了不适':
            task['feeling']=feelings[condition]
    for key,destination in (('date','requestedDate'),('time','requestedTime')):
        if key in data:
            value=string(data,key,10 if key=='date' else 5)
            if value:
                try:
                    decoded = date.fromisoformat(value) if key=='date' else time.fromisoformat(value)
                    if (str(decoded) if key=='date' else decoded.isoformat(timespec='minutes'))!=value:
                        raise ValueError()
                except ValueError:
                    raise RequestError('请输入有效的可用日期和起始时间。')
                task[destination]=value
            else:
                task.pop(destination,None)
    if scenario == 'ball' and (data.get('date') or data.get('time')):
        task['explicitMove'] = True
    if scenario=='ball' or 'date' in data or 'time' in data:
        task.pop('calendarUnclear',None)
        task.pop('requestedPeriod',None)


def active_goal(ctx):
    end = ctx.get('goalContext',{}).get('endDate','')
    return ctx['profile']['goal'] if not end or end>=str(today()) else ''


def known_ball_game(ctx, task):
    if ctx.get('profileConfirmed') or task.get('example'):
        return ctx.get('goalContext', {})
    return {}


def ball_impact(ctx, task, selected_day):
    game=known_ball_game(ctx, task)
    event=game.get('eventName')
    event_day=game.get('eventDate','')
    if not event or event_day<str(today()):
        return '未登记近期球局，影响未知。'
    if event_day==selected_day:
        return f'{event}（{event_day}）保留；同日是否冲突，请确认实际球局时段。'
    return f'{event}（{event_day}）保留，仍按原日期。'


def restrictions_for(ctx, task):
    restrictions = re.split(r'[、，,；;和与及]',task.get('restriction',''))
    restrictions.extend(x[1] for x in RESTRICTION.finditer(ctx['profile']['constraint']))
    return {RESTRICTION.sub(lambda m:m[1],x.strip(),count=1).strip() for x in restrictions if x.strip()}


def eligibility(ctx, task, option, *, reschedule=False):
    title=option['title']
    if not reschedule:
        source=option.get('source','')
        if not (source.startswith('用户确认') or (task.get('example') and source.startswith('示例备选'))):
            return 'source', '备选来源还未经你确认。'
        if option['minutes']>=task['original']['minutes']:
            return 'time', '没有缩短原训练时长。'
    if task['minutes'] is not None and option['minutes']>task['minutes']:
        return 'time', f"超出这次可用的 {task['minutes']} 分钟。"
    if task['feeling']=='今天有些疲劳' and option.get('intensity')!='light' and not reschedule:
        return 'condition', '本次偏累，只展示你已有的低负荷备选。'
    active_content = ' '.join(x for x in re.split(r'[。；;]',option.get('content','')) if not re.search(r'不包含|不做|无需|去掉|移除|省略',x))
    content = ' '.join((title,option.get('purpose',''),option.get('equipment',''),active_content))
    restriction = next((x for x in sorted(restrictions_for(ctx,task)) if x in content), None)
    if restriction:
        return 'restriction', f'包含本次排除的内容或器械：{restriction}。'
    focus = {term for term in FOCUS if term in active_goal(ctx)}
    if not reschedule and focus and not (focus.intersection(option.get('goalTags',[])) or any(term in content for term in focus)):
        return 'goal', '未明确保留当前目标的训练重点。'
    required = set(option['equipmentRequired']) if 'equipmentRequired' in option else equipment_tokens(option.get('equipment',''))
    available = task.get('availableEquipment')
    if required and not available and not reschedule:
        return 'equipment_missing', '需要先确认这次可用器械。'
    if required and available:
        absent = required - equipment_tokens(available)
        if absent:
            return 'equipment', '缺少所需器械：'+'、'.join(sorted(absent))+'。'
    return '', ''


def next_options(ctx, task):
    plan = task['original']
    options = []
    excluded = []
    if task['kind']!='reschedule' or task['move'] is False:
        if plan['date']<str(today()):
            return options, excluded
        if plan.get('actions'):
            return basketball_options(ctx, task, plan)
        for alt in ctx.get('alternatives',ALT_PLANS):
            code, reason = eligibility(ctx,task,alt)
            if code:
                excluded.append({'title':alt['title'],'code':code,'reason':reason})
                continue
            retain = alt.get('retained') or alt.get('purpose') or active_goal(ctx) or '沿用你认可的备选内容'
            change = alt.get('changed') or f"将原 {plan['minutes']} 分钟安排替换为 {alt['minutes']} 分钟的备选。"
            reason = f"在 {task['minutes'] if task['minutes'] is not None else plan['minutes']} 分钟内沿用已有备选。"
            if task['feeling']=='今天有些疲劳':
                reason += ' 本次本人报告偏累，采用已确认的低负荷备选。'
            elif task.get('priorFeedbackUsed'):
                reason += ' 上次练后记录被用于补问，以你确认的当日状态为准。'
            options.append(dict(alt,date=plan['date'],time=plan['time'],reason=reason,changes={
                'retained':retain,'changed':change,'ballImpact':ball_impact(ctx,task,plan['date'])}))
        options.sort(key=lambda opt:(opt.get('intensity')=='light',-opt['minutes']))
    else:
        day,clock=task.get('requestedDate'),task.get('requestedTime')
        code, reason=eligibility(ctx,task,plan,reschedule=True)
        if code:
            excluded.append({'title':plan['title'],'code':code,'reason':reason})
        elif day and clock and day>=str(today()) and day not in task.get('excludedDates',[]) and clock_minutes(clock)+plan['minutes']<=1440:
            proposed=datetime.combine(date.fromisoformat(day),time.fromisoformat(clock)).astimezone()
            if proposed>datetime.now().astimezone():
                options.append({**plan,'id':'reschedule','date':day,'time':clock,'requiresAvailabilityConfirmation':True,
                    'reason':'待你确认空闲：尚未接入日历。请确认新时段及训练器械可用。沿用原训练内容与时长。',
                    'changes':{'retained':f"保留原训练内容和 {plan['minutes']} 分钟时长。",'changed':f'改到 {day} {clock}。','ballImpact':ball_impact(ctx,task,day)}})
    return options[:3],excluded


def basketball_options(ctx, task, plan):
    def blocked(code, reason):
        return [], [{'title': plan['title'], 'code': code, 'reason': reason}]

    if not training.enabled():
        return blocked('catalog_unavailable', '此计划的篮球动作库仍待审核。')
    start = datetime.combine(date.fromisoformat(plan['date']), time.fromisoformat(plan['time'])).astimezone()
    if start <= datetime.now().astimezone():
        return blocked('slot_conflict', '原训练的开始时段已过，请先选新的可用时段。')
    if task['feeling'] == '今天有些疲劳':
        return blocked('condition', '偏累时需要已确认的低负荷备选；这个动作清单暂时没有。')
    if task.get('space') is None:
        return blocked('space_missing', '请确认这次准备在哪里训练。')
    if not task.get('availableEquipment'):
        return blocked('equipment_missing', '请确认这次可用器械。')

    available = equipment_tokens(task['availableEquipment'])
    restrictions = restrictions_for(ctx, task)
    current_actions, edits, omitted = [], [], []
    for action in plan['actions']:
        replacement, reason = training.compatible_action(
            action, available, task['space'], task.get('anchorAvailable'), restrictions)
        if replacement is None:
            if action.get('optional'):
                omitted.append(action['exerciseName'])
                continue
            if reason == 'anchor_missing':
                return blocked(reason, f'{action["exerciseName"]}的替代动作需要确认固定点。')
            return blocked('no_eligible_action', f'暂无符合场地和器械条件、且保留 {action["exerciseName"]} 目的的替代动作。')
        current_actions.append((action, replacement))

    budget = min(plan['minutes'], task['minutes'] if task['minutes'] is not None else plan['minutes']) * 60
    required_seconds = sum(replacement['estimatedSeconds'] for _, replacement in current_actions)
    for index in reversed(range(len(current_actions))):
        if required_seconds <= budget:
            break
        action, replacement = current_actions[index]
        if action.get('optional'):
            omitted.append(action['exerciseName'])
            required_seconds -= replacement['estimatedSeconds']
            del current_actions[index]
    if required_seconds > budget:
        return blocked('time', '保留关键动作的预计时长超出可用时段。')
    if not current_actions:
        return blocked('no_eligible_action', '当前没有符合条件的动作。')

    index = training.exercises_by_id()
    actions = [replacement for _, replacement in current_actions]
    for original, replacement in current_actions:
        if original['exerciseId'] != replacement['exerciseId']:
            edits.append(f'{original["exerciseName"]} → {replacement["exerciseName"]}')
    edits.extend(f'移除辅助动作 {name}' for name in omitted)
    if not edits:
        edits.append('按动作及组间休息估算训练时长，保留动作顺序')
    equipment = sorted({item for action in actions for item in index[action['exerciseId']]['equipment']})
    purpose = plan.get('purpose') or active_goal(ctx)
    impact = ball_impact(ctx, task, plan['date'])
    same_day = task.get('sameDayBall') and plan['date'] == str(today())
    if same_day:
        impact = f'今晚临时球局保留。请核对训练与实际球局时段是否冲突。{impact}'
    location = {'home': '居家', 'gym': '健身房', 'court': '球场'}[task['space']]
    reason = '按可用时间、场地和器械检查已选动作及草稿中的替代关系。预计时长含组间休息。'
    if task.get('priorFeedbackUsed'):
        reason += ' 上次练后记录用于补问，本次采用你确认的当日状态。'
    return [{
        **plan,
        'id': 'basketball_adjustment',
        'title': f'篮球体能 · {location}调整',
        'space': task['space'],
        'minutes': math.ceil(required_seconds / 60),
        'equipment': '、'.join(equipment) if equipment else '徒手',
        'content': '、'.join(action['exerciseName'] for action in actions),
        'source': '篮球体能预览 · 待教练审核',
        'actions': actions,
        'requiresAvailabilityConfirmation': bool(same_day),
        'reason': reason,
        'changes': {'retained': purpose or '原计划动作的训练目的和顺序',
                    'changed': '；'.join(edits), 'ballImpact': impact},
    }], []


def prepare(ctx, task):
    task["draftVersion"] += 1
    task["question"] = ""
    task["options"] = []
    task['excludedCandidates'] = []
    task["contextVersion"] = ctx["contextVersion"]
    task["expiresAt"] = (datetime.now().astimezone()+timedelta(minutes=30)).isoformat(timespec="seconds")
    if (task['original'].get('actions') and task['kind'] == 'reschedule' and task['minutes'] is not None
            and BALL_CHANGE.search(task['input']) and not task.get('explicitMove')):
        task.update(kind='shorten', move=False)
        for key in ('requestedDate','requestedTime','requestedPeriod','calendarUnclear'):
            task.pop(key, None)
    request_context={'condition':{'未报告明显不适':'normal','今天有些疲劳':'tired','报告了不适':'pain'}.get(task['feeling'],'unknown')}
    for source,key in (('minutes','minutes'),('availableEquipment','equipment'),('restriction','restriction'),('requestedDate','date'),('requestedTime','time'),('space','space'),('anchorAvailable','anchorAvailable')):
        if task.get(source) is not None:
            request_context[key]=task[source]
    scenario='ball' if task['move'] is True or task['kind']=='reschedule' else 'short' if task['kind']=='shorten' else 'tired' if task['kind']=='fatigue' else None
    if scenario:
        request_context['scenario']=scenario
    if 'sleepChanged' in task:
        request_context['sleepChanged']=task['sleepChanged']
    task['requestContext']=request_context
    task["evidence"], task["unknowns"] = facts(ctx, task)
    if task["feeling"] == "报告了不适" or safety(ctx["profile"]["constraint"]):
        task["reason"] = "已记录不适或运动限制，暂停自动调整。请先寻求合适的专业帮助。"
        transition(task,"stopped")
        return
    if not task["kind"]:
        task["question"] = "这次想缩短训练、调整日期，还是因疲劳选择已有的轻量方案？"
    elif task.get("calendarUnclear"):
        task["question"] = "这段日期或时段无法准确匹配。请给出一个明确日期与起始时间，或保留原安排手动调整。"
    elif task['move'] is not False and task['kind']=='reschedule' and not (task.get('requestedDate') and task.get('requestedTime')):
        if task.get('requestedDate'):
            task['question'] = f"{task['requestedDate']} 几点方便开始力量训练？"
        elif task.get('requestedTime'):
            task['question'] = f"哪一天的 {task['requestedTime']} 可以开始力量训练？"
        else:
            task['question'] = '力量训练可以改到哪一天、几点？周末球局会保留。'
    elif task["kind"] == "shorten" and task["minutes"] is None:
        task["question"] = "今天有多少分钟可以留给训练？"
    elif not task['feeling']:
        latest = next(iter(recent_sessions(ctx,task)),None)
        basketball = latest and latest.get('exercise') == 'basketball'
        if basketball and latest['performedAt'] < str(today() - timedelta(days=1)):
            latest = None
        if latest and (latest.get('discomfort') or (latest['completion'] in ('completed','partial') and latest['feeling']=='偏累')):
            task['priorFeedbackUsed']=True
            if latest['discomfort']:
                activity = '篮球' if basketball else '训练'
                task['question']=f'上一次{activity}记录有不适。今天状态正常、仍偏累，还是也有明显不适？'
            else:
                actual='部分完成' if latest['completion']=='partial' else '完成'
                activity = '篮球' if basketball else ''
                task['question']=f"上一次{actual}{activity} {latest['minutes']} 分钟并记录偏累。今天状态正常、仍偏累，还是有明显不适？"
        else:
            task['question']='今天状态正常、有些疲劳，还是有明显不适？'
    else:
        task['options'],task['excludedCandidates']=next_options(ctx,task)
        if any(x['code']=='equipment_missing' for x in task['excludedCandidates']):
            task['options']=[]
            task['question']='今天能用哪些器械？可以回答哑铃、弹力带、徒手，或说明器械未知。'
        elif any(x['code']=='space_missing' for x in task['excludedCandidates']):
            task['question']='这次在家里、健身房还是球场训练？'
        elif any(x['code']=='anchor_missing' for x in task['excludedCandidates']):
            task['question']='这次有合适的弹力带固定点吗？请回答有合适的固定点，或没有固定点。'
        elif not task['options']:
            if task['excludedCandidates']:
                detail = task['excludedCandidates'][0]['reason'] if task['original'].get('actions') else '已有备选无法满足这次条件。'
                task['question']=f'{detail}你可以保留原安排，也可提供新的可用日期和起始时间。'
            elif task.get('requestedDate') or task.get('requestedTime'):
                task["question"] = "指定时间已过去、相互冲突或无法容纳原训练。请给出新的日期与起始时间，或保留原安排。"
            else:
                task["question"] = "已有备选无法满足这次条件。是否愿意改期？也可以保留原安排手动调整。"
    if task["question"]:
        task["reason"] = "还需要确认本次调整的条件。"
        transition(task,"needs_info")
    else:
        task["reason"] = ('已根据原动作和当次条件拟好篮球训练草稿。选择后仍需你确认。'
                          if task['original'].get('actions') else
                          "已根据原安排、当日自述及已确认的备选拟好草稿。选择后仍需你确认。")
        transition(task,"draft")


def create(ctx, body):
    s = string(body,"input",500,True)
    created = stamp()
    t = {"id":uuid.uuid4().hex,"input":s,"createdAt":created,"updatedAt":created,"original":ctx["plan"].copy(),
         "draftVersion":0,"selectedId":None,"receipt":None,"feedback":None,"mode":"rules","timeline":[],
         "minutes":None,"move":None,"kind":None,"feeling":"","answers":[],
         'example':'示例' in ctx['plan'].get('source','') and not ctx.get('profileConfirmed')}
    note_input(t,s,body.get("_intent"),body.get("_interpretation"))
    note_context(t,body)
    prepare(ctx,t)
    return t


def require_open(t):
    if t["status"] not in OPEN_STATES:
        raise RequestError("这次任务已经结束，请发起新的调整。","task_closed",409)


def confirmation_option(ctx,t,body):
    version = integer(body.get("draftVersion"),1,2**31-1)
    option_id = string(body,"optionId",60,True)
    remind = boolean(body.get("remind",False))
    if t["status"] in ("saved","partial"):
        raise RequestError("此任务已有确认回执，请发起新的调整。","already_confirmed",409)
    require_open(t)
    if t["status"] != "draft":
        raise RequestError("信息尚未补齐，暂不能确认。","draft_required",409)
    if t.get("expiresAt") and datetime.fromisoformat(t["expiresAt"]) < datetime.now().astimezone():
        raise RequestError("草稿已过期，请刷新条件后重新确认。","draft_expired",409)
    if not ctx["permissions"]["save"]:
        raise RequestError("尚未授权保存计划。请在设置中开启，或保留原安排。","save_denied",403)
    if version != t["draftVersion"] or ctx["plan"]["version"] != t["original"]["version"] or ctx["contextVersion"] != t["contextVersion"]:
        raise RequestError("计划、授权或上下文已更新，请重新生成草稿并确认。","stale_draft",409)
    option = next((x for x in t["options"] if x["id"] == option_id),None)
    if not option:
        raise RequestError("请从当前草稿中选择一个方案。")
    if option.get("actions") and not training.enabled():
        raise RequestError("请在本地篮球体能预览中确认动作计划。", "catalog_unavailable", 403)
    if option.get("requiresAvailabilityConfirmation") and body.get("availabilityConfirmed") is not True:
        if option["id"] == "basketball_adjustment":
            raise RequestError("请确认训练时段与实际球局不冲突。", "availability_confirmation_required")
        raise RequestError("请确认这个改期时段对你可用；当前未接入日历。","availability_confirmation_required")
    proposed = datetime.combine(date.fromisoformat(option["date"]),time.fromisoformat(option["time"])).astimezone()
    if option["date"] < str(today()) or ((option_id == "reschedule" or option.get("actions")) and proposed <= datetime.now().astimezone()):
        raise RequestError("这个时段已经失效，请重新发起调整。","slot_conflict",409)
    return option,remind


def confirm(ctx,t,body,operation_id):
    option,remind = confirmation_option(ctx,t,body)
    ctx["plan"].update({k:option[k] for k in ("title","date","time","minutes")})
    ctx["plan"].update({k:option.get(k,'') for k in ('purpose','content','equipment')})
    if "actions" in option:
        ctx["plan"].update({key:option[key] for key in ('actions','templateId','space','catalogVersion') if key in option})
    ctx["plan"]["version"] += 1
    ctx["plan"]["source"] = "示例计划 · 已确认调整" if '示例' in t['original'].get('source','') else "用户确认 · 本地计划"
    t["selectedId"] = option["id"]
    t["requestedReminder"] = remind
    followup = remind and ctx["permissions"]["reminder"]
    message = "新安排已保存到本机。"
    if remind:
        message += "已在应用内登记练后跟进。" if followup else "未授权跟进，提醒未设置。"
    end_time = datetime.combine(date.fromisoformat(option["date"]),time.fromisoformat(option["time"]))+timedelta(minutes=option["minutes"])
    t["receipt"] = {"planSaved":True,"reminderSaved":followup,"message":message,
                    "followupAt":end_time.isoformat(timespec="minutes") if followup else None,
                    "operationId":operation_id,"at":stamp(),"planVersion":ctx["plan"]["version"]}
    transition(t,"partial" if remind and not followup else "saved")


def update_settings(ctx, body):
    if 'goalContext' in body:
        gc=body['goalContext']
        if not isinstance(gc,dict): raise RequestError('阶段信息格式不正确。')
        values={k:string(gc,k,n) for k,n in (('endDate',10),('eventName',100),('eventDate',10))}
        for k in ('endDate','eventDate'):
            if values[k]:
                try:
                    if str(date.fromisoformat(values[k]))!=values[k]:raise ValueError()
                except ValueError:raise RequestError('请填写有效日期。')
        ctx['goalContext']=values
        ctx['contextVersion']+=1
    if "exerciseGoals" in body:
        from video_engine.exercises import EXERCISES
        values=body["exerciseGoals"]
        if not isinstance(values,dict) or any(k not in EXERCISES for k in values): raise RequestError("动作目标格式不正确。")
        ctx["exerciseGoals"]={k:integer(v,0,1000) for k,v in values.items()}
    if "trainingPreferences" in body:
        values=body["trainingPreferences"]
        if not isinstance(values,dict): raise RequestError("设置格式不正确。")
        ctx["trainingPreferences"]={k:boolean(v) for k,v in values.items() if k in ("sound","speak","skeleton","mirror")}
    changed = False
    if "weeklyGoal" in body:
        ctx["weeklyGoal"] = integer(body["weeklyGoal"],1,7)
    for section, fields in (("profile",PROFILE_FIELDS),("permissions",set(ctx["permissions"]))):
        patch = body.get(section,{})
        if not isinstance(patch,dict) or patch.keys()-fields:
            raise RequestError("设置字段无效。")
        if section=="profile" and patch:
            ctx["profileConfirmed"]=True
            ctx["profileAt"]=stamp()
            changed=True
        for key,value in patch.items():
            val = string(patch,key) if section=="profile" else boolean(value)
            if ctx[section][key] != val:
                ctx[section][key] = val
                if section == "profile":
                    ctx["profileAt"] = stamp()
                if section == "profile" or key == "device":
                    changed = True
    if changed:
        ctx["contextVersion"] += 1


def view_state(db,ctx):
    history=[]
    active=None
    for row, in db.execute("SELECT data FROM tasks ORDER BY rowid DESC"):
        t = json.loads(row)
        if not ctx["permissions"]["device"]:
            t["evidence"] = [x for x in t["evidence"] if not x.get("device")]
        if t["id"] == ctx["active"]:
            active = t
        history.append(t)
    catalog_view = {'trainingCatalog': training.catalog(), 'activeWorkout': ctx.get('activeWorkout')} if training.enabled() else {}
    return {"today":str(today()),"plan":ctx["plan"],"profile":ctx["profile"],"profileAt":ctx["profileAt"],
            "permissions":ctx["permissions"],"device":device(ctx),"activity":dict(ctx["activity"],isExample="模拟" in ctx["activity"].get("source", "")),
            "profileConfirmed":ctx.get("profileConfirmed",False),"planIsExample":"示例" in ctx["plan"].get("source", ""),"goalContext":ctx.get('goalContext',{}),
            "alternatives":ctx["alternatives"],"activeTask":active,"history":history,"experience":ctx.get('experience'),
            **mobile.state_extra(db,ctx), **catalog_view}


def get_task(db,body):
    ident = string(body,"id",64,True)
    row = db.execute("SELECT data FROM tasks WHERE id=?",(ident,)).fetchone()
    if not row:
        raise RequestError("未找到任务，请刷新后重试。","not_found",404)
    return json.loads(row[0])


def write(db,ctx,path,body):
    if path=="/api/reset":
        db.execute("DELETE FROM tasks")
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM video_jobs")
        db.execute("DELETE FROM operations")
        db.execute("DELETE FROM operation_recoveries")
        db.execute("DELETE FROM analytics_events")
        db.execute("DELETE FROM intent_diagnostics")
        fresh=seeded()
        mobile.initialize(db,fresh)
        return fresh
    if path=="/api/plan":
        mobile.edit_plan(ctx,body)
        return ctx
    if path=="/api/alternatives":
        mobile.edit_alternatives(ctx,body)
        return ctx
    if path=="/api/settings":
        update_settings(ctx,body)
        return ctx
    if path=="/api/wearable/disconnect":
        ctx.pop('wearable',None);ctx['realDeviceOnly']=True;ctx['permissions']['device']=False;ctx['contextVersion']+=1
        return ctx
    if path=="/api/wearable":
        from wearable import summarize, when
        if '_parsed' in body:
            w=body['_parsed']
        else:
            rows=body.get('records',[])
            if not isinstance(rows,list) or len(rows)>100: raise RequestError('设备记录格式不正确。')
            w=summarize(rows,'Bluetooth')
        prior=ctx.get('wearable',{})
        bykey={r['key']:r for r in prior.get('metrics',[])}
        bykey.update({r['key']:r for r in w['metrics'] if r['key'] not in bykey or when(r['at'])>=when(bykey[r['key']]['at'])})
        w['metrics']=list(bykey.values())
        w['sourceNames']=sorted(set(r['source'] for r in w['metrics']))
        ctx['wearable']=w;ctx['realDeviceOnly']=True;ctx['permissions']['device']=True;ctx['contextVersion']+=1
        return ctx
    if path=="/api/device":
        mode = string(body,"mode",25,True)
        if mode not in DEVICE_MODES:
            raise RequestError("未知的模拟设备状态。")
        if ctx["deviceMode"] != mode:
            ctx["deviceMode"] = mode
            ctx["contextVersion"] += 1
        return ctx
    if path=="/api/tasks":
        t=create(ctx,body)
        db.execute("INSERT INTO tasks VALUES(?,?)",(t["id"],encode(t)))
        analytics.record(db,"adjust_start",{"taskId":t["id"],"scenario":t["kind"] or "unknown", "draftVersion":t["draftVersion"]})
    else:
        if path not in ("/api/answer","/api/keep","/api/cancel","/api/feedback"):
            raise RequestError("接口不存在。","not_found",404)
        t=get_task(db,body)
        ident=t["id"]
        if path=="/api/answer":
            require_open(t)
            answer=string(body,"text",500,True)
            t["answers"].append(answer)
            t["updatedAt"]=stamp()
            t["original"]=ctx["plan"].copy()
            fatigue_blocked = t['original'].get('actions') and any(
                candidate.get('code') == 'condition' for candidate in t.get('excludedCandidates', []))
            if fatigue_blocked:
                # A different slot can take the original duration and equipment.
                # Only keep newly entered conditions when the user opts to move.
                old_minutes, old_equipment = t['minutes'], t.pop('availableEquipment', None)
                t['minutes'] = None
            note_input(t,answer,body.get("_intent"),body.get("_interpretation"))
            note_context(t,body)
            if fatigue_blocked and t.get('move') is not True:
                if t['minutes'] is None:
                    t['minutes'] = old_minutes
                if old_equipment:
                    t.setdefault('availableEquipment', old_equipment)
            prepare(ctx,t)
            analytics.record(db,"clarify_answer",{"taskId":t["id"],"round":len(t["answers"]),"draftVersion":t["draftVersion"]})
        elif path in ("/api/cancel","/api/keep"):
            require_open(t)
            kept = path == "/api/keep"
            t["reason"] = "已保留正在使用的安排。" if kept else "已取消本次调整。"
            t["options"]=[]
            transition(t,"kept" if kept else "cancelled")
        else:
            if t["status"] not in ("saved","partial"):
                raise RequestError("请先确认并保存安排，再填写执行反馈。","plan_not_saved",409)
            done=boolean(body.get("done"))
            minutes=integer(body.get("minutes"),0,1440)
            feeling=string(body,"feeling",100)
            note=string(body,"note",500)
            t["feedback"]={"done":done,"minutes":minutes,"feeling":feeling,"note":note,"at":stamp()}
            t["updatedAt"]=stamp()
            # Legacy clients also contribute a structured actual-feedback record.
            mobile.save_session(db,ctx,{"taskId":ident,"completion":"completed" if done and minutes else "not_done",
                "minutes":minutes if done else 0,"feeling":feeling if feeling in ("合适","偏累","偏轻松","不合适") else "合适",
                "discomfort":safety(feeling+note),"note":note})
        db.execute("UPDATE tasks SET data=? WHERE id=?",(encode(t),t["id"]))
    if path in ("/api/tasks","/api/answer") and "_interpretation" in body:
        analytics.record_interpretation(db,body["_interpretation"],body["_intent_diagnostics"],t)
    ctx["active"]=t["id"]
    return ctx


def dispatch(db_path,method,path,body):
    if method not in ("GET","POST","DELETE"):
        return 405,{"code":"method_not_allowed","error":"不支持此请求方式。"}
    if not isinstance(body,dict):
        return 400,{"code":"invalid_input","error":"请求内容须为对象。"}
    started=monotonic_time.monotonic()
    db=sqlite3.connect(db_path,timeout=8)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            ctx=bootstrap(db)
            extra={}
            if method=="POST" and path=="/api/events":
                return 200,{"event":analytics.ingest(db,body)}
            if method=="GET" and path.startswith("/api/operations/"):
                return 200,{"operation":mobile.lookup_operation(db,path.rsplit("/",1)[-1])}
            if method=="POST" and path=="/api/confirm/check":
                key,digest,prior=mobile.operation(db,body,"/api/confirm")
                if prior:
                    return 200,{"operation":prior}
                task=get_task(db,body)
                confirmation_option(ctx,task,body)
                # The immediate transaction serializes this check with a
                # confirmation. Reserve the exact payload for any late
                # original request or a deliberate same-key recovery.
                return 200,{"operation":mobile.reserve_operation_recovery(db,key,digest,task["id"])}
            if method=="DELETE" and path.startswith("/api/sessions/"):
                ident=path.rsplit("/",1)[-1]
                mobile.get_record(db,"sessions",ident)
                db.execute("DELETE FROM sessions WHERE id=?",(ident,))
                mobile.refresh_context(db,ctx)
            elif method=="POST":
                if path in workout.ROUTES:
                    workout.require_preview()
                prior=None
                if path in ("/api/confirm","/api/sessions",workout.FINISH):
                    # Legacy desktop confirms remain compatible; new PWA always supplies a key.
                    if path=="/api/confirm" and not body.get("idempotencyKey"):
                        body=dict(body,idempotencyKey="legacy_"+str(body.get("id",""))+"_"+str(body.get("draftVersion","")))
                    key,digest,prior=mobile.operation(db,body,path)
                if prior:
                    extra["operation"]=prior
                    if prior.get("sessionId"):
                        extra["savedSessionId"]=prior["sessionId"]
                elif path==workout.START:
                    workout.start(db,ctx,body)
                elif path==workout.ACTION:
                    workout.update_action(ctx,body)
                elif path==workout.DISCARD:
                    workout.discard(ctx,body)
                elif path==workout.FINISH:
                    ident=workout.finish(db,ctx,body)
                    extra["savedSessionId"]=ident
                    extra["operation"]=mobile.remember_operation(db,key,digest,{"sessionId":ident})
                elif path in ("/api/sessions","/api/sessions/update"):
                    ident=mobile.save_session(db,ctx,body,path.endswith("update"))
                    extra["savedSessionId"]=ident
                    if path=="/api/sessions":
                        extra["operation"]=mobile.remember_operation(db,key,digest,{"sessionId":ident})
                elif path=="/api/confirm":
                    task=get_task(db,body)
                    confirm(ctx,task,body,uuid.uuid4().hex)
                    db.execute("UPDATE tasks SET data=? WHERE id=?",(encode(task),task["id"]))
                    ctx["active"]=task["id"]
                    receipt=task["receipt"]
                    extra["operation"]=mobile.remember_operation(db,key,digest,
                        {"taskId":task["id"],"planVersion":receipt["planVersion"]},
                        operation_id=receipt["operationId"],at=receipt["at"])
                    selected=task["selectedId"]
                    analytics.record(db,"plan_confirm",{"taskId":task["id"],"draftVersion":task["draftVersion"],
                        "optionId":selected if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",selected) else "custom"})
                    analytics.record(db,"operation_finished",{"taskId":task["id"],"operationId":receipt["operationId"],
                        "result":"succeeded","latencyMs":round((monotonic_time.monotonic()-started)*1000,2)})
                else:
                    ctx=write(db,ctx,path,body)
            elif method=="GET":
                if path not in ("/api/state","/api/export"):
                    raise RequestError("接口不存在。","not_found",404)
            else:
                raise RequestError("接口不存在。","not_found",404)
            if method!="GET":
                if path!="/api/reset":
                    ctx["pristine"]=False
                db.execute("UPDATE workspace SET data=? WHERE id=1",(encode(ctx),))
            result={**view_state(db,ctx),**extra}
            if path=="/api/export":
                result.update(events=analytics.list_events(db),exportedAt=stamp(),mediaNote="此文件包含结构化记录，不含原始视频。")
        return 200,result
    except RequestError as exc:
        if method=="POST" and path in ("/api/tasks","/api/answer") and "_interpretation" in body:
            with db:
                analytics.initialize_interpretations(db)
                analytics.record_interpretation(db,body["_interpretation"],body["_intent_diagnostics"])
        if path=="/api/confirm" and method=="POST":
            # The failed business transaction has rolled back. Record only its
            # safe outcome, never the submitted text or pairing credentials.
            with db:
                task_id=body.get("id")
                if isinstance(task_id,str) and re.fullmatch(r"[0-9a-f]{32}",task_id) and db.execute("SELECT 1 FROM tasks WHERE id=?",(task_id,)).fetchone():
                    analytics.record(db,"operation_finished",{"taskId":task_id,"result":"conflict" if exc.status==409 else "rejected",
                        "reasonCode":exc.code,"latencyMs":round((monotonic_time.monotonic()-started)*1000,2)})
        return exc.status,{"code":exc.code,"error":str(exc)}
    finally:
        db.close()
