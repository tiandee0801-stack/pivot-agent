"""Persist resumable workouts and finish through the existing session record."""

import json
import uuid

import mobile_records
import training_catalog


START = '/api/workout/start'
ACTION = '/api/workout/action'
FINISH = '/api/workout/finish'
DISCARD = '/api/workout/discard'
ROUTES = frozenset((START, ACTION, FINISH, DISCARD))


def require_preview():
    from engine import RequestError

    if not training_catalog.enabled():
        raise RequestError('进行中训练仅在本机训练预览开放。', 'catalog_unavailable', 403)


def start(db, ctx, body):
    from engine import RequestError, integer, stamp

    revision = integer(body.get('planVersion'), 1, 2**31-1)
    # A second start or a retry returns the frozen plan already being trained.
    if ctx.get('activeWorkout'):
        return
    plan = ctx['plan']
    if plan['version'] != revision:
        raise RequestError('训练计划已更新，请刷新后开始。', 'stale_plan', 409)
    if not plan.get('actions'):
        raise RequestError('请先保存一套包含动作的训练计划。', 'workout_no_plan', 409)
    task_id = None
    for data, in db.execute('SELECT data FROM tasks ORDER BY rowid DESC'):
        task = json.loads(data)
        receipt = task.get('receipt') or {}
        if receipt.get('planSaved') and receipt.get('planVersion') == revision:
            task_id = task['id']
            break
    at = stamp()
    ctx['activeWorkout'] = {
        'id': uuid.uuid4().hex,
        'revision': 1,
        'title': plan['title'],
        'planVersion': revision,
        'planDate': plan['date'],
        'planTime': plan['time'],
        'plannedMinutes': plan['minutes'],
        'taskId': task_id,
        'startedAt': at,
        'updatedAt': at,
        'actions': [dict(action, status='pending') for action in plan['actions']],
    }


def _expected_workout(ctx, body):
    from engine import RequestError, integer, string

    ident = string(body, 'id', 64, True)
    workout = ctx.get('activeWorkout')
    if not workout or workout['id'] != ident:
        raise RequestError('未找到这份进行中训练，请刷新查看。', 'workout_not_found', 404)
    if integer(body.get('expectedRevision'), 1, 2**31-1) != workout['revision']:
        raise RequestError('训练进度已更新，请刷新后继续。', 'stale_workout', 409)
    return workout


def update_action(ctx, body):
    from engine import RequestError, integer, stamp, string

    workout = _expected_workout(ctx, body)
    index = integer(body.get('index'), 0, len(workout['actions'])-1)
    status = string(body, 'status', 16, True)
    if status not in ('pending', 'completed', 'skipped'):
        raise RequestError('请选择有效的动作完成状态。')
    action = workout['actions'][index]
    if status == 'completed':
        entry = body.get('entry')
        if not isinstance(entry, dict) or entry.get('exerciseId') != action['exerciseId']:
            raise RequestError('实际记录需对应当前训练动作。')
        actual, = training_catalog.session_entries({'exerciseEntries': [entry]}, None, 'completed')
        if actual['metric'] != action['metric']:
            raise RequestError('此动作的记录单位已更新，请刷新动作库后重新开始。', 'workout_catalog_changed', 409)
    elif status == 'skipped':
        reason = string(body, 'reason', 120)

    action['status'] = status
    action.pop('entry', None)
    action.pop('reason', None)
    if status == 'completed':
        action['entry'] = dict(actual, exerciseName=action['exerciseName'])
    elif status == 'skipped' and reason:
        action['reason'] = reason
    workout['revision'] += 1
    workout['updatedAt'] = stamp()


def discard(ctx, body):
    _expected_workout(ctx, body)
    ctx.pop('activeWorkout')


def finish(db, ctx, body):
    from engine import RequestError

    workout = _expected_workout(ctx, body)
    entries = [action['entry'] for action in workout['actions'] if action['status'] == 'completed']
    if not entries:
        raise RequestError('请至少记录一个实际完成的动作，再保存此次训练。', 'workout_empty', 409)
    payload = {
        'completion': 'completed' if len(entries) == len(workout['actions']) else 'partial',
        'minutes': body.get('minutes'),
        'feeling': body.get('feeling'),
        'discomfort': body.get('discomfort', False),
        'note': body.get('note', ''),
        'performedAt': workout['startedAt'][:10],
        'exerciseEntries': entries,
    }
    if workout['taskId']:
        payload['taskId'] = workout['taskId']
    saved_id = mobile_records.save_session(db, ctx, payload, workout=workout)
    ctx.pop('activeWorkout')
    return saved_id
