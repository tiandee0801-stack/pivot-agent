"""Basketball preview regressions through the transactional API dispatcher."""

import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from engine import dispatch


SCENARIO = "今晚临时约了球，今天只有30分钟，家里只有弹力带，状态正常。"


class BasketballPreviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = str(Path(folder.name) / "preview.sqlite3")
        environment = patch.dict("os.environ", {"PIVOT_CATALOG_PREVIEW": "1", "PIVOT_PUBLIC_ORIGIN": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.state = self.call("GET", "/api/state")

    def call(self, method, path, payload=None, expected=200):
        status, response = dispatch(self.db, method, path, payload or {})
        self.assertEqual(status, expected, response if status != 200 else path)
        return response

    def save_template(self, ident="gym_lower_body_core", **changes):
        template = next(item for item in self.state["trainingCatalog"]["templates"] if item["id"] == ident)
        payload = {
            "title": template["title"], "purpose": template["purpose"], "date": self.state["today"],
            "time": "23:59", "minutes": template["minutes"], "expectedVersion": self.state["plan"]["version"],
            "templateId": template["id"], "actions": template["actions"], **changes,
        }
        self.state = self.call("POST", "/api/plan", payload)
        return self.state["plan"]

    def draft(self, **context):
        return self.call("POST", "/api/tasks", {"input": SCENARIO, "context": context})["activeTask"]

    def answer(self, task, text):
        return self.call("POST", "/api/answer", {"id": task["id"], "text": text})["activeTask"]

    def confirmation(self, task):
        return {"id": task["id"], "draftVersion": task["draftVersion"], "optionId": task["options"][0]["id"],
                "availabilityConfirmed": True, "idempotencyKey": "basketball-test-confirmation"}

    def log_ball_game(self, **changes):
        yesterday = str(date.fromisoformat(self.state['today']) - timedelta(days=1))
        state = self.call('POST', '/api/sessions', {
            'idempotencyKey': 'yesterday-ball-session', 'exercise': 'basketball', 'exerciseName': '篮球',
            'completion': 'completed', 'minutes': 52, 'feeling': '偏累', 'discomfort': False,
            'performedAt': yesterday, **changes,
        })
        return next(record for record in state['sessions'] if record['id'] == state['savedSessionId'])

    def test_ball_record_stays_real_when_plan_switches_from_demo(self):
        self.assertTrue(self.state['planIsExample'])
        actual = self.log_ball_game()
        demo = self.log_ball_game(idempotencyKey='demo-ball-session', minutes=20, note='[示例体验反馈]')
        self.assertFalse(actual['example'])
        self.assertTrue(demo['example'])
        original = self.save_template()
        task = self.draft(anchorAvailable=True)
        cited = [item for item in task['evidence'] if item.get('sessionId')]
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0], {
            'label': '篮球记录', 'source': '用户训练记录', 'value': '篮球 · 52 分钟 · 偏累',
            'at': actual['performedAt'], 'sessionId': actual['id'], 'revision': actual['revision'],
            'exercise': 'basketball', 'exerciseName': '篮球', 'minutes': 52, 'completion': 'completed', 'feeling': '偏累',
        })
        self.assertEqual(task['requestContext']['condition'], 'normal')
        self.assertEqual(self.call('GET', '/api/state')['plan'], original)

    def test_old_standalone_ball_log_recovers_from_missing_cache(self):
        record = self.log_ball_game()
        with sqlite3.connect(self.db) as connection:
            old = dict(record, example=True)
            connection.execute('UPDATE sessions SET data=? WHERE id=?', (json.dumps(old), record['id']))
            ctx = json.loads(connection.execute('SELECT data FROM workspace WHERE id=1').fetchone()[0])
            ctx.pop('sessionProvenanceVersion')
            ctx['recentSessions'] = []
            connection.execute('UPDATE workspace SET data=? WHERE id=1', (json.dumps(ctx),))
        self.save_template()
        state = self.call('GET', '/api/state')
        self.assertFalse(state['sessions'][0]['example'])
        self.assertTrue(any(item.get('sessionId') == record['id'] for item in self.draft(anchorAvailable=True)['evidence']))
        with sqlite3.connect(self.db) as connection:
            stored = json.loads(connection.execute('SELECT data FROM sessions WHERE id=?', (record['id'],)).fetchone()[0])
        self.assertTrue(stored['example'])
        self.assertEqual(stored['revision'], record['revision'])

    def test_yesterday_tired_today_25_minutes_can_keep_move_or_confirm(self):
        self.log_ball_game()
        clock = date.fromisoformat(self.state['today'])
        tomorrow = str(clock + timedelta(days=1))
        original = self.save_template(date=tomorrow)
        request = {'input': '今天只有25分钟，家里只有弹力带。', 'context': {'anchorAvailable': True}}
        task = self.call('POST', '/api/tasks', request)['activeTask']
        self.assertIn('篮球 52 分钟并记录偏累', task['question'])
        self.assertEqual(task['options'], [])
        tired = self.answer(task, '今天仍偏累。')
        self.assertEqual(tired['options'], [])
        self.assertEqual(tired['excludedCandidates'][0]['code'], 'condition')
        kept = self.call('POST', '/api/keep', {'id': task['id']})
        self.assertEqual(kept['activeTask']['status'], 'kept')
        self.assertEqual(kept['plan'], original)

        task = self.call('POST', '/api/tasks', request)['activeTask']
        tired = self.answer(task, '今天仍偏累。')
        next_day = str(clock + timedelta(days=2))
        moved = self.call('POST', '/api/answer', {'id': tired['id'], 'text': '改期',
            'context': {'scenario': 'ball', 'date': next_day, 'time': '19:15'}})['activeTask']
        self.assertEqual(moved['status'], 'draft')
        move_option = moved['options'][0]
        self.assertEqual((move_option['id'], move_option['date'], move_option['minutes']), ('reschedule', next_day, original['minutes']))
        self.assertEqual(move_option['actions'], original['actions'])
        self.call('POST', '/api/confirm', {**self.confirmation(moved), 'availabilityConfirmed': False}, 400)
        self.assertEqual(self.call('GET', '/api/state')['plan'], original)

        task = self.call('POST', '/api/tasks', request)['activeTask']
        normal = self.answer(task, '今天状态正常。')
        option = normal['options'][0]
        self.assertLessEqual(option['minutes'], 25)
        self.assertIn('哑铃划船 → 弹力带划船', option['changes']['changed'])
        self.assertEqual(self.call('GET', '/api/state')['plan'], original)
        saved = self.call('POST', '/api/confirm', self.confirmation(normal))
        self.assertEqual(saved['plan']['actions'], option['actions'])
        workout = self.call('POST', '/api/workout/start', {'planVersion': saved['plan']['version']})['activeWorkout']
        self.assertEqual(workout['planVersion'], saved['plan']['version'])
        self.assertEqual([action['exerciseId'] for action in workout['actions']], [action['exerciseId'] for action in option['actions']])

    def test_catalog_flag_and_public_origin_gate(self):
        catalog = self.state["trainingCatalog"]
        self.assertEqual(catalog["reviewStatus"], "pending")
        self.assertEqual(len(catalog["templates"]), 3)
        self.assertTrue(50 <= len(catalog["exercises"]) <= 60)
        for env in [{"PIVOT_CATALOG_PREVIEW": "0"}, {"PIVOT_PUBLIC_ORIGIN": "https://preview.invalid"}]:
            with self.subTest(env=env), patch.dict("os.environ", env):
                self.assertNotIn("trainingCatalog", self.call("GET", "/api/state"))
                plan = self.state["plan"]
                self.call("POST", "/api/plan", {
                    "title": plan["title"], "date": plan["date"], "time": plan["time"],
                    "expectedVersion": plan["version"], "minutes": plan["minutes"], "actions": [],
                }, 403)

    def test_three_templates_and_duration_validation(self):
        for template in self.state["trainingCatalog"]["templates"]:
            plan = self.save_template(template["id"])
            self.assertEqual([row["exerciseId"] for row in plan["actions"]],
                             [row["exerciseId"] for row in template["actions"]])
            self.assertTrue(all(row["exerciseName"] and row["metric"] for row in plan["actions"]))
        payload = {"title": plan["title"], "date": plan["date"], "time": plan["time"],
                   "expectedVersion": plan["version"], "minutes": 1}
        self.call("POST", "/api/plan", payload, 400)
        self.assertEqual(self.call("GET", "/api/state")["plan"], plan)

    def test_anchor_missing_refused_and_confirmation_idempotent(self):
        plan = self.save_template()
        pending = self.draft()
        self.assertIn("固定点", pending["question"])
        denied = self.answer(pending, "没有固定点。")
        self.assertEqual(denied["status"], "needs_info")
        self.assertFalse(denied["options"])
        ready = self.answer(denied, "确认有合适的弹力带固定点。")
        option = ready["options"][0]
        self.assertEqual([item["exerciseId"] for item in option["actions"]],
                         ["squat", "band_rdl", "band_row", "side_plank"])
        self.assertLessEqual(option["minutes"], 30)
        self.assertIn("哑铃划船 → 弹力带划船", option["changes"]["changed"])
        self.assertIn("今晚临时球局", option["changes"]["ballImpact"])
        self.assertEqual(self.call("GET", "/api/state")["plan"], plan)
        payload = self.confirmation(ready)
        self.call("POST", "/api/confirm", {**payload, "availabilityConfirmed": False}, 400)
        saved = self.call("POST", "/api/confirm", payload)
        self.assertEqual(saved["plan"]["actions"], option["actions"])
        self.assertEqual(saved["plan"]["space"], "home")
        duplicated = self.call("POST", "/api/confirm", payload)
        self.assertEqual(duplicated["operation"], saved["operation"])
        self.assertEqual(duplicated["plan"]["version"], plan["version"] + 1)
        self.assertEqual(self.call("GET", "/api/state")["history"][0]["options"][0]["actions"], option["actions"])

    def test_restrictions_conditions_and_stale_plan_hold(self):
        plan = self.save_template()
        restriction = self.draft(anchorAvailable=True, restriction="上肢水平拉")
        self.assertEqual(restriction["status"], "needs_info")
        self.assertFalse(restriction["options"])
        self.assertEqual(self.draft(anchorAvailable=True, condition="pain")["status"], "stopped")
        ready = self.draft(anchorAvailable=True)
        self.call("POST", "/api/plan", {"title": "已编辑训练", "date": plan["date"], "time": plan["time"],
                                        "minutes": plan["minutes"], "expectedVersion": plan["version"]})
        result = self.call("POST", "/api/confirm", self.confirmation(ready), 409)
        self.assertEqual(result["code"], "stale_draft")
        self.assertEqual(self.call("GET", "/api/state")["plan"]["actions"], plan["actions"])

    def test_reschedule_preserves_ordered_actions(self):
        plan = self.save_template()
        tomorrow = (date.fromisoformat(plan["date"]) + timedelta(days=1)).isoformat()
        task = self.call("POST", "/api/tasks", {
            "input": "想改期，状态正常。", "context": {"scenario": "ball", "date": tomorrow, "time": "15:00"},
        })["activeTask"]
        self.assertEqual(task["options"][0]["id"], "reschedule")
        saved = self.call("POST", "/api/confirm", self.confirmation(task))
        self.assertEqual(saved["plan"]["actions"], plan["actions"])
        self.assertEqual(saved["plan"]["date"], tomorrow)

    def test_multi_action_session_checks_metric_and_retains_snapshots(self):
        rows = [
            {"exerciseId": "band_row", "sets": 2, "reps": 8},
            {"exerciseId": "side_plank", "seconds": 20},
            {"exerciseId": "short_acceleration", "distanceMeters": 20, "seconds": 10, "rounds": 2},
            {"exerciseId": "court_shuttle", "rounds": 3, "distanceMeters": 30, "seconds": 45},
        ]
        base = {"idempotencyKey": "basketball-test-session", "completion": "partial",
                "minutes": 12, "feeling": "合适", "discomfort": False}
        self.call("POST", "/api/sessions", {**base, "exerciseEntries": [{"exerciseId": "side_plank", "reps": 4}]}, 400)
        created = self.call("POST", "/api/sessions", {**base, "exerciseEntries": rows})
        self.assertEqual(created["sessions"][0]["exerciseEntries"],
                         self.call("GET", "/api/state")["sessions"][0]["exerciseEntries"])
        self.assertEqual([item["metric"] for item in created["sessions"][0]["exerciseEntries"]],
                         ["reps", "time", "distance", "rounds"])
        self.assertEqual(created["sessions"][0]["exerciseEntries"][2]["distanceMeters"], 20)
        repeated = self.call("POST", "/api/sessions", {**base, "exerciseEntries": rows})
        self.assertEqual(repeated["savedSessionId"], created["savedSessionId"])
        changed = self.call("POST", "/api/sessions/update", {
            **base, "id": created["savedSessionId"], "expectedRevision": 1, "exerciseEntries": rows[:2],
        })
        self.assertEqual(len(changed["sessions"][0]["exerciseEntries"]), 2)


if __name__ == "__main__":
    unittest.main()
