"""Exercise the resumable workout API with isolated visitor workspaces."""

from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from engine import dispatch


class WorkoutTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / 'visitor.sqlite3'
        self.other_db = Path(folder.name) / 'other-visitor.sqlite3'
        environment = patch.dict('os.environ', {'PIVOT_CATALOG_PREVIEW': '1', 'PIVOT_PUBLIC_ORIGIN': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def request(self, path='/api/state', body=None, status=200, db=None):
        actual, result = dispatch(db or self.db, 'GET' if body is None else 'POST', path, body or {})
        self.assertEqual(actual, status, result)
        return result

    def plan(self, title='三项训练', actions=None):
        state = self.request()
        response = self.request('/api/plan', {
            'title': title, 'date': state['today'], 'time': '18:30', 'minutes': 30,
            'expectedVersion': state['plan']['version'],
            'actions': actions or [
                {'exerciseId': 'squat', 'sets': 2, 'quantity': 8, 'restSeconds': 45},
                {'exerciseId': 'side_plank', 'sets': 2, 'quantity': 20},
                {'exerciseId': 'short_acceleration', 'sets': 1, 'quantity': 10},
            ],
        })
        return response['plan']

    def start(self, plan):
        state = self.request('/api/workout/start', {'planVersion': plan['version']})
        return state['activeWorkout']

    def action(self, workout, index, action_status, status=200, **fields):
        return self.request('/api/workout/action', {
            'id': workout['id'], 'expectedRevision': workout['revision'],
            'index': index, 'status': action_status, **fields,
        }, status)

    def finish_payload(self, workout, **fields):
        return {
            'id': workout['id'], 'expectedRevision': workout['revision'],
            'idempotencyKey': 'workout-test-finish', 'minutes': 12, 'feeling': '合适', **fields,
        }

    def test_start_requires_saved_actions_and_pins_plan(self):
        initial = self.request()
        self.assertIsNone(initial['activeWorkout'])
        error = self.request('/api/workout/start', {'planVersion': initial['plan']['version']}, 409)
        self.assertEqual(error['code'], 'workout_no_plan')
        plan = self.plan()
        stale = self.request('/api/workout/start', {'planVersion': initial['plan']['version']}, 409)
        self.assertEqual(stale['code'], 'stale_plan')
        active = self.start(plan)
        self.assertEqual(self.start(plan), active)
        self.assertEqual(self.request()['sessions'], [])
        self.assertEqual(active['planVersion'], plan['version'])
        self.assertEqual([action['status'] for action in active['actions']], ['pending'] * 3)
        self.assertEqual([action['exerciseId'] for action in active['actions']],
                         [action['exerciseId'] for action in plan['actions']])
        updated_plan = self.plan('编辑后的计划', [{'exerciseId': 'pushup', 'sets': 1, 'quantity': 5}])
        self.assertEqual(self.start(updated_plan), active)
        self.assertEqual(self.request(db=self.other_db)['activeWorkout'], None)
        self.request('/api/workout/discard', {
            'id': active['id'], 'expectedRevision': active['revision'],
        }, 404, db=self.other_db)

    def test_keeps_progress_and_rejects_stale_or_mismatched_updates(self):
        active = self.start(self.plan())
        self.action(active, 0, 'completed', 400, entry={'exerciseId': 'side_plank', 'seconds': 15})
        self.action(active, 1, 'completed', 400, entry={'exerciseId': 'side_plank', 'reps': 5})
        self.assertEqual(self.request()['activeWorkout'], active)
        current = self.action(active, 0, 'completed',
                              entry={'exerciseId': 'squat', 'sets': 2, 'reps': 15})['activeWorkout']
        self.assertEqual(self.action(active, 1, 'skipped', 409)['code'], 'stale_workout')
        current = self.action(current, 1, 'skipped', reason='场地临时占用')['activeWorkout']
        self.assertEqual(self.request()['activeWorkout'], current)
        self.assertEqual(current['actions'][0]['entry']['reps'], 15)
        self.assertEqual(current['actions'][1]['reason'], '场地临时占用')
        reopened = self.action(current, 1, 'pending')['activeWorkout']
        self.assertEqual(reopened['actions'][1]['status'], 'pending')
        self.assertNotIn('reason', reopened['actions'][1])
        self.assertEqual(self.request()['sessions'], [])

    def test_finishes_partial_once_and_copies_outcome_history(self):
        active = self.start(self.plan())
        empty = self.request('/api/workout/finish', self.finish_payload(active), 409)
        self.assertEqual(empty['code'], 'workout_empty')
        current = self.action(active, 0, 'completed',
                              entry={'exerciseId': 'squat', 'sets': 1, 'reps': 6})['activeWorkout']
        current = self.action(current, 1, 'skipped', reason='器械不可用')['activeWorkout']
        payload = self.finish_payload(current)
        self.assertEqual(self.request('/api/workout/finish', {**payload, 'minutes': 0}, 400)['code'],
                         'invalid_input')
        self.assertEqual(self.request()['activeWorkout'], current)
        self.assertEqual(self.request()['sessions'], [])
        result = self.request('/api/workout/finish', payload)
        self.assertIsNone(result['activeWorkout'])
        saved, = result['sessions']
        self.assertEqual(result['savedSessionId'], saved['id'])
        self.assertEqual(saved['workoutPlanVersion'], active['planVersion'])
        self.assertEqual(saved['completion'], 'partial')
        self.assertEqual(saved['workoutActions'], current['actions'])
        self.assertEqual(saved['exerciseEntries'], [current['actions'][0]['entry']])
        retry = self.request('/api/workout/finish', payload)
        self.assertEqual(retry['operation'], result['operation'])
        self.assertEqual(retry['sessions'], [saved])
        receipt = self.request('/api/operations/' + result['operation']['operationId'])
        self.assertEqual(receipt['operation'], result['operation'])
        self.assertEqual(self.request('/api/workout/finish', {**payload, 'minutes': 13}, 409)['code'],
                         'idempotency_conflict')
        patched, = self.request('/api/sessions/update', {
            'id': saved['id'], 'expectedRevision': saved['revision'], 'completion': 'partial',
            'minutes': 13, 'feeling': '偏累', 'discomfort': False,
            'exerciseEntries': [{'exerciseId': 'squat', 'sets': 1, 'reps': 8}],
        })['sessions']
        self.assertEqual(patched['workoutActions'], current['actions'])
        self.assertEqual(patched['exerciseEntries'][0]['reps'], 8)

    def test_all_actions_complete_and_discard_leaves_record_intact(self):
        plan = self.plan(actions=[{'exerciseId': 'side_plank', 'sets': 2, 'quantity': 20}])
        active = self.start(plan)
        current = self.action(active, 0, 'completed', entry={'exerciseId': 'side_plank', 'seconds': 16})['activeWorkout']
        saved, = self.request('/api/workout/finish', self.finish_payload(current))['sessions']
        self.assertEqual(saved['completion'], 'completed')
        self.assertEqual(saved['exerciseEntries'][0]['seconds'], 16)
        another = self.start(plan)
        self.assertNotEqual(another['id'], active['id'])
        result = self.request('/api/workout/discard', {'id': another['id'], 'expectedRevision': another['revision']})
        self.assertIsNone(result['activeWorkout'])
        self.assertEqual(result['sessions'], [saved])

    def test_preview_gate_covers_state_and_mutations(self):
        active = self.start(self.plan())
        with patch.dict('os.environ', {'PIVOT_CATALOG_PREVIEW': '0'}):
            self.assertNotIn('activeWorkout', self.request())
            response = self.request('/api/workout/discard', {
                'id': active['id'], 'expectedRevision': active['revision'],
            }, 403)
            self.assertEqual(response['code'], 'catalog_unavailable')
        self.assertEqual(self.request()['activeWorkout'], active)

    def test_associates_the_matching_confirmed_plan_version(self):
        plan = self.plan(actions=[{'exerciseId': 'side_plank', 'sets': 2, 'quantity': 20}])
        tomorrow = (date.fromisoformat(plan['date']) + timedelta(days=1)).isoformat()
        task = self.request('/api/tasks', {
            'input': '想改期，状态正常。',
            'context': {'scenario': 'ball', 'date': tomorrow, 'time': '15:00'},
        })['activeTask']
        confirmed = self.request('/api/confirm', {
            'id': task['id'], 'draftVersion': task['draftVersion'], 'optionId': task['options'][0]['id'],
            'idempotencyKey': 'workout-test-confirm', 'availabilityConfirmed': True,
        })['plan']
        active = self.start(confirmed)
        self.assertEqual(active['taskId'], task['id'])
        self.assertEqual(active['planDate'], tomorrow)
        current = self.action(active, 0, 'completed', entry={'exerciseId': 'side_plank', 'seconds': 16})['activeWorkout']
        saved, = self.request('/api/workout/finish', self.finish_payload(current))['sessions']
        self.assertEqual(saved['taskId'], task['id'])
        self.assertEqual(saved['performedAt'], active['startedAt'][:10])
        self.assertIsNone(self.start(self.plan(title='再次编辑的计划'))['taskId'])
