import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import Future
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import intent
from guest_spaces import GuestSpaces
from mobile_backend import VideoManager
from server import PivotHandler


SHORT = '今天只有30分钟，只有弹力带，状态正常'
ASK_EQUIPMENT = '今天只有30分钟，状态正常'
VALID_INTENT = {'kind': 'shorten', 'minutes': 30, 'discomfort': False}


class LocalIntentTests(unittest.TestCase):
    def runner(self):
        model = intent.LocalIntent(enabled=False)
        model._load_job = Future()
        model._pool = Mock()
        return model

    def test_disabled_weights_and_load_failures_are_distinct(self):
        self.assertEqual(intent.LocalIntent(enabled=False).interpret(SHORT).reason, 'model_disabled')
        with patch.object(intent, 'WEIGHTS', Path('/nonexistent/test-pivot-weights')):
            self.assertEqual(intent.LocalIntent().interpret(SHORT).reason, 'weights_missing')
        model = self.runner()
        model._load_job.set_exception(RuntimeError('offline test load error'))
        result = model.interpret(SHORT)
        self.assertEqual(result.reason, 'load_error')
        self.assertIsNone(result.intent)
        self.assertFalse(model._gate.locked())

    def test_load_timeout_releases_the_gate(self):
        model = self.runner()
        with patch.object(intent, 'LOAD_TIMEOUT', 0):
            result = model.interpret(SHORT)
        self.assertEqual(result.reason, 'load_timeout')
        self.assertIsNone(result.intent)
        self.assertFalse(model._gate.locked())
        model._pool.submit.assert_not_called()

    def test_generation_timeout_holds_the_gate_until_late_finish(self):
        model = self.runner()
        model._load_job.set_result(object())
        late_work = Future()
        model._pool.submit.return_value = late_work
        with patch.object(intent, 'GENERATION_TIMEOUT', 0):
            timeout = model.interpret(SHORT)
        self.assertEqual(timeout.reason, 'generation_timeout')
        self.assertIsNone(timeout.intent)
        self.assertTrue(model._gate.locked())
        self.assertEqual(model.interpret(SHORT).reason, 'model_busy')
        self.assertEqual(model._pool.submit.call_count, 1)

        late_work.set_result((VALID_INTENT, 1))
        self.assertFalse(model._gate.locked())
        self.assertIsNone(timeout.intent)
        recovered = model.interpret(SHORT)
        self.assertEqual(recovered.intent, VALID_INTENT)
        self.assertEqual(recovered.attempts, 1)

    def test_reports_retry_count_and_invalid_output(self):
        model = self.runner()
        model._load_job.set_result(object())
        for output, reason in ((VALID_INTENT, None), (None, 'invalid_output')):
            with self.subTest(reason=reason):
                work = Future()
                work.set_result((output, 2))
                model._pool.submit.return_value = work
                result = model.interpret(SHORT)
                self.assertEqual((result.intent, result.reason, result.attempts), (output, reason, 2))


class InterpretationHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        base = VideoManager(root / 'base.sqlite3')
        self.addCleanup(base.pool.shutdown)
        self.spaces = GuestSpaces(root / 'visitors')
        self.addCleanup(self.close_spaces)
        self.model = Mock()
        self.model.info.return_value = {'available': True, 'label': 'Test fixture'}
        handler = partial(
            PivotHandler, db_path=str(root / 'base.sqlite3'),
            video=base, model=self.model, pairing=self.spaces,
        )
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.origin = f'http://127.0.0.1:{server.server_port}'

    def close_spaces(self):
        for _, video in self.spaces.managers.values():
            video.pool.shutdown()

    def new_client(self):
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar

    def request(self, client, path, body=None, status=200):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.origin + path, data=data, headers={'Content-Type': 'application/json'},
        )
        try:
            response = client.open(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            self.assertEqual(response.status, status, result)
            return result

    def outcome(self, source):
        if source == 'model':
            return intent.IntentResult(intent=VALID_INTENT, reason=None, attempts=1, elapsed_ms=1)
        return intent.IntentResult(intent=None, reason='model_busy', attempts=0, elapsed_ms=0)

    def attribution(self, task, source):
        values = task['interpretation']
        self.assertEqual(values['source'], source)
        self.assertIsInstance(values['requestId'], str)
        self.assertTrue(values['requestId'])
        self.assertNotIn('reason', values)
        return values

    def test_latest_source_follows_each_request_in_both_directions(self):
        for first, second in (('model', 'fallback_rules'), ('fallback_rules', 'model')):
            with self.subTest(first=first, second=second):
                client, jar = self.new_client()
                self.model.interpret.side_effect = [self.outcome(first), self.outcome(second)]
                initial = self.request(client, '/api/tasks', {'input': ASK_EQUIPMENT})
                task = initial['activeTask']
                self.assertTrue(initial['model']['available'])
                self.assertEqual(task['status'], 'needs_info')
                self.assertIn('哪些器械', task['question'])
                first_turn = self.attribution(task, first)

                updated = self.request(client, '/api/answer', {'id': task['id'], 'text': '只有弹力带'})
                self.assertEqual(updated['plan'], initial['plan'])
                revised = updated['activeTask']
                self.assertEqual(revised['id'], task['id'])
                self.assertEqual(revised['status'], 'draft')
                second_turn = self.attribution(revised, second)
                self.assertNotEqual(first_turn['requestId'], second_turn['requestId'])
                refreshed = self.request(client, '/api/state')['activeTask']
                self.assertEqual(refreshed['interpretation'], second_turn)

                db, _ = self.spaces.workspace(next(iter(jar)).value)
                with sqlite3.connect(db) as connection:
                    rows = connection.execute(
                        'SELECT request_id, turn, source, reason, attempts '
                        'FROM intent_diagnostics WHERE task_id=? ORDER BY turn', (task['id'],),
                    ).fetchall()
                self.assertEqual(rows, [
                    (first_turn['requestId'], 0, first, self.outcome(first).reason, self.outcome(first).attempts),
                    (second_turn['requestId'], 1, second, self.outcome(second).reason, self.outcome(second).attempts),
                ])

    def test_structured_initial_request_skips_model_and_free_text_answer_uses_it(self):
        client, _ = self.new_client()
        self.model.interpret.return_value = self.outcome('model')
        state = self.request(client, '/api/tasks', {
            'input': ASK_EQUIPMENT,
            'entry': 'quick',
            'context': {'scenario': 'short', 'minutes': 30, 'condition': 'normal'},
        })
        task = state['activeTask']
        self.assertEqual(task['status'], 'needs_info')
        self.attribution(task, 'structured_rules')
        self.model.interpret.assert_not_called()

        updated = self.request(client, '/api/answer', {'id': task['id'], 'text': '弹力带'})
        self.attribution(updated['activeTask'], 'model')
        self.model.interpret.assert_called_once_with('弹力带')

    def test_fallback_preserves_constraints_and_requires_single_confirm(self):
        client, _ = self.new_client()
        self.model.interpret.return_value = self.outcome('fallback_rules')
        original = self.request(client, '/api/state')['plan']
        self.assertEqual(original['minutes'], 60)
        response = self.request(client, '/api/tasks', {'input': SHORT})
        task = response['activeTask']
        self.assertEqual(response['plan'], original)
        self.assertEqual(task['status'], 'draft')
        self.assertIsNone(task['receipt'])
        turn = self.attribution(task, 'fallback_rules')
        self.assertTrue(task['options'])
        self.assertTrue(all(option['minutes'] <= 30 for option in task['options']))
        self.assertTrue(any('哑铃' in candidate['reason'] for candidate in task['excludedCandidates']))

        confirm = {
            'id': task['id'], 'draftVersion': task['draftVersion'],
            'optionId': task['options'][0]['id'], 'idempotencyKey': 'v112_fallback_confirm',
        }
        saved = self.request(client, '/api/confirm', confirm)
        repeated = self.request(client, '/api/confirm', confirm)
        self.assertEqual(saved['operation'], repeated['operation'])
        self.assertEqual(saved['plan']['version'], original['version'] + 1)
        self.assertEqual(repeated['plan'], saved['plan'])
        self.assertEqual(saved['activeTask']['interpretation'], turn)

        lookup_path = '/api/operations/' + saved['operation']['operationId']
        self.assertEqual(self.request(client, lookup_path)['operation'], saved['operation'])
        fresh_client, _ = self.new_client()
        self.request(fresh_client, lookup_path, status=404)

        feedback = self.request(client, '/api/sessions', {
            'taskId': task['id'], 'completion': 'partial', 'minutes': 20, 'feeling': '偏累',
            'discomfort': False, 'idempotencyKey': 'v112_partial_feedback',
        })
        self.assertEqual(feedback['activeTask']['interpretation'], turn)
        self.assertEqual(feedback['sessions'][0]['completion'], 'partial')
        self.model.interpret.assert_called_once_with(SHORT)

    def test_reported_discomfort_stops_adjustment_on_both_paths(self):
        for source in ('model', 'fallback_rules'):
            with self.subTest(source=source):
                client, _ = self.new_client()
                self.model.interpret.return_value = self.outcome(source)
                original = self.request(client, '/api/state')['plan']
                state = self.request(client, '/api/tasks', {'input': '今天只有30分钟，现在明显不适'})
                task = state['activeTask']
                self.attribution(task, source)
                self.assertEqual(task['status'], 'stopped')
                self.assertEqual(task['options'], [])
                self.assertEqual(state['plan'], original)

    def test_legacy_task_remains_without_turn_attribution(self):
        client, jar = self.new_client()
        self.model.interpret.return_value = self.outcome('model')
        task = self.request(client, '/api/tasks', {'input': SHORT})['activeTask']
        db, _ = self.spaces.workspace(next(iter(jar)).value)
        task.pop('interpretation')
        with sqlite3.connect(db) as connection:
            connection.execute('UPDATE tasks SET data=? WHERE id=?', (json.dumps(task), task['id']))
        reloaded = self.request(client, '/api/state')['activeTask']
        self.assertEqual(reloaded['mode'], 'model')
        self.assertFalse(reloaded.get('interpretation'))


if __name__ == '__main__':
    unittest.main()
