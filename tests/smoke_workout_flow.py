"""Run the resumable workout flow against a disposable guest-mode server."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

from smoke_basketball_preview import Guest, form_for


APP = Path(__file__).resolve().parents[1]


def start_server(db, port):
    env = {**os.environ, 'PIVOT_GUEST_MODE': '1', 'PIVOT_CATALOG_PREVIEW': '1', 'PIVOT_PUBLIC_ORIGIN': ''}
    process = subprocess.Popen(
        [sys.executable, '-u', str(APP / 'server.py'), '--port', str(port), '--db', str(db), '--rules-only'],
        cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for line in process.stdout:
        match = re.search(r'http://127\.0\.0\.1:(\d+)', line)
        if match:
            return process, match[0], int(match[1])
    raise AssertionError(f'Server did not start (code {process.wait()})')


def stop(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    process.stdout.close()


def transition(guest, workout, index, status, **fields):
    return guest.request('workout/action', {
        'id': workout['id'], 'expectedRevision': workout['revision'],
        'index': index, 'status': status, **fields,
    })['activeWorkout']


def main():
    with tempfile.TemporaryDirectory(prefix='pivot-workout-') as target:
        db = Path(target) / 'base.sqlite3'
        process, origin, port = start_server(db, 0)
        try:
            guest = Guest(origin)
            ready = guest.request('state')
            assert not ready.get('activeWorkout')
            template = next(item for item in ready['trainingCatalog']['templates']
                            if item['id'] == 'gym_lower_body_core')
            plan = guest.request('plan', form_for(ready['plan'], template))['plan']
            body = {'planVersion': plan['version']}
            workout = guest.request('workout/start', body)['activeWorkout']
            assert guest.request('workout/start', body)['activeWorkout']['id'] == workout['id']
            entry = {'exerciseId': workout['actions'][0]['exerciseId'], 'sets': 2, 'reps': 12, 'weight': 8}
            workout = transition(guest, workout, 0, 'completed', entry=entry)
            workout = transition(guest, workout, 1, 'skipped', reason='器械暂时不可用')
            assert not Guest(origin).request('state').get('activeWorkout')
            assert guest.request('state')['activeWorkout'] == workout

            stop(process)
            process, _, _ = start_server(db, port)
            assert guest.request('state')['activeWorkout'] == workout
            timer_index = next(i for i, item in enumerate(workout['actions']) if item['metric'] == 'time')
            workout = transition(guest, workout, timer_index, 'completed',
                                 entry={'exerciseId': workout['actions'][timer_index]['exerciseId'], 'seconds': 18})
            finished = {
                'id': workout['id'], 'expectedRevision': workout['revision'], 'minutes': 12,
                'feeling': '合适', 'discomfort': False, 'idempotencyKey': uuid4().hex,
            }
            result = guest.request('workout/finish', finished)
            assert not result.get('activeWorkout')
            assert guest.request('workout/finish', finished)['operation'] == result['operation']
            history = guest.request('state')['sessions']
            assert len(history) == 1 and history[0]['id'] == result['savedSessionId']
            record = history[0]
            assert record['completion'] == 'partial' and record['workoutPlanVersion'] == plan['version']
            assert record['workoutActions'][1]['reason'] == '器械暂时不可用'
            assert record['workoutActions'][1]['status'] == 'skipped'
            assert record['exerciseEntries'][0]['reps'] == 12 and record['exerciseEntries'][1]['seconds'] == 18
            print('Workout start, actuals, skip, isolated restart, partial finish and receipt replay passed.')
        finally:
            stop(process)


if __name__ == '__main__':
    main()
