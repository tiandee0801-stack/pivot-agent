"""Minimal local product events, without user text, notes or credentials.

Pass an existing sqlite3 connection. Mutations participate in the caller's
transaction; this module never commits or changes business state.
"""
from datetime import datetime
import json
import math
import re
import uuid

SERVER_EVENTS = frozenset({
    'adjust_start', 'clarify_answer', 'plan_confirm', 'operation_finished',
    'training_recorded', 'video_submitted', 'video_finished', 'observation_confirmed',
})
CLIENT_EVENTS = frozenset({'draft_view'})
FIELDS = frozenset({
    'taskId', 'scenario', 'round', 'draftVersion', 'optionId', 'operationId',
    'result', 'latencyMs', 'sessionId', 'completion', 'revision', 'jobId',
    'status', 'quality', 'durationSeconds', 'corrected', 'reasonCode',
})
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$')
TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
ENUMS = {
    'scenario': {'shorten', 'reschedule', 'fatigue', 'maintain', 'other', 'unknown'},
    'completion': {'completed', 'partial', 'not_done'},
    'quality': {'usable', 'insufficient'},
    'result': {'success', 'succeeded', 'failed', 'error', 'saved', 'partial', 'unknown',
               'conflict', 'rejected', 'cancelled', 'kept', 'needs_info', 'draft', 'blocked'},
    'status': {'queued', 'running', 'done', 'error', 'success', 'succeeded', 'failed',
               'saved', 'partial', 'unknown', 'conflict', 'rejected', 'cancelled', 'kept',
               'needs_info', 'draft', 'blocked'},
}


def error(message, code='invalid_event', status=400):
    # engine imports analytics; avoid a module-level cycle.
    from engine import RequestError
    raise RequestError(message, code, status)


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS analytics_events(id TEXT PRIMARY KEY, data TEXT NOT NULL)')


def initialize_interpretations(db):
    db.execute('''CREATE TABLE IF NOT EXISTS intent_diagnostics(
        request_id TEXT PRIMARY KEY, task_id TEXT, turn INTEGER, source TEXT NOT NULL,
        reason TEXT, readiness TEXT NOT NULL, attempts INTEGER, parse_ms INTEGER NOT NULL,
        outcome TEXT NOT NULL, draft_version INTEGER, created_at INTEGER NOT NULL
    )''')
    db.execute("DELETE FROM intent_diagnostics WHERE created_at < strftime('%s','now','-30 days')")


def record_interpretation(db, attribution, diagnostics, task=None):
    # Only server-classified values are stored. The task contributes identifiers,
    # never the submitted text or model response.
    db.execute('''INSERT INTO intent_diagnostics VALUES(
        ?,?,?,?,?,?,?,?,?,?,strftime('%s','now')
    )''', (
        attribution['requestId'], task['id'] if task else None,
        len(task['answers']) if task else None, attribution['source'],
        diagnostics['reason'], diagnostics['readiness'], diagnostics['attempts'],
        diagnostics['parseMs'], 'accepted' if task else 'rejected',
        task['draftVersion'] if task else None,
    ))


def validate_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        error('事件标识格式无效。')
    return value


def safe_fields(fields):
    if not isinstance(fields, dict):
        error('事件字段格式无效。')
    clean = {}
    for key, value in fields.items():
        if key not in FIELDS or value is None:
            continue
        if key in ('taskId', 'operationId', 'sessionId', 'jobId'):
            validate_id(value)
        elif key in ('optionId', 'reasonCode'):
            if not isinstance(value, str) or not TOKEN.fullmatch(value):
                error('事件分类字段格式无效。')
        elif key in ENUMS:
            if not isinstance(value, str) or value not in ENUMS[key]:
                error('事件状态无效。')
        elif key in ('round', 'draftVersion', 'revision'):
            if type(value) is not int or not 0 <= value <= 2**31-1:
                error('事件版本格式无效。')
        elif key in ('latencyMs', 'durationSeconds'):
            limit = 3_600_000 if key == 'latencyMs' else 86400
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= limit:
                error('事件耗时格式无效。')
        elif key == 'corrected' and type(value) is not bool:
            error('事件校正状态无效。')
        clean[key] = value
    return clean


def _existing(db, event_id, event, fields, source):
    row = db.execute('SELECT data FROM analytics_events WHERE id=?', (event_id,)).fetchone()
    if row is None:
        return None
    saved = json.loads(row[0])
    payload = {k:v for k,v in saved.items() if k not in ('createdAt', 'eventId')}
    if payload != {'event':event, 'source':source, **fields}:
        error('同一事件标识不能提交不同内容。', 'event_conflict', 409)
    return saved


def _store(db, event, fields, event_id, source):
    existing = _existing(db, event_id, event, fields, source)
    if existing is not None:
        return existing
    obj = {'eventId':event_id, 'event':event,
           'createdAt':datetime.now().astimezone().isoformat(timespec='milliseconds'),
           'source':source, **fields}
    encoded = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    db.execute('INSERT OR IGNORE INTO analytics_events(id,data) VALUES(?,?)', (event_id, encoded))
    return _existing(db, event_id, event, fields, source)


def record(db, event_name, fields, event_id=None):
    """Record a server event. Unlisted fields are discarded before serialization."""
    if not isinstance(event_name, str) or event_name not in SERVER_EVENTS:
        error('不支持的服务端事件。')
    initialize(db)
    return _store(db, event_name, safe_fields(fields),
                  validate_id(event_id) if event_id is not None else uuid.uuid4().hex, 'server')


def ingest(db, body):
    """Accept only an observed client draft view; never trust client outcomes."""
    if not isinstance(body, dict) or set(body) != {'eventId', 'event', 'taskId', 'draftVersion'}:
        error('仅接受草稿浏览事件所需字段。')
    if not isinstance(body['event'], str) or body['event'] not in CLIENT_EVENTS:
        error('不支持的客户端事件。')
    event_id = validate_id(body['eventId'])
    fields = safe_fields({k:body[k] for k in ('taskId', 'draftVersion')})
    if set(fields) != {'taskId', 'draftVersion'} or fields['draftVersion'] < 1:
        error('草稿浏览事件缺少有效版本。')
    initialize(db)
    # A valid original retry remains idempotent after a task has evolved.
    existing = _existing(db, event_id, body['event'], fields, 'client')
    if existing is not None:
        return existing
    row = db.execute('SELECT data FROM tasks WHERE id=?', (fields['taskId'],)).fetchone()
    if row is None:
        error('关联任务不存在。', 'not_found', 404)
    task = json.loads(row[0])
    if task.get('draftVersion') != fields['draftVersion']:
        error('草稿已更新，请读取最新版本。', 'draft_conflict', 409)
    return _store(db, body['event'], fields, event_id, 'client')


def list_events(db):
    initialize(db)
    return [json.loads(row[0]) for row in db.execute('SELECT data FROM analytics_events ORDER BY rowid')]
