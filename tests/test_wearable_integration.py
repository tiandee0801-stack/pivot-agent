"""CSV import -> persistent device context -> plan-adjustment evidence."""
import csv
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import dispatch
from wearable import parse_export


class WearableIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'wearable.sqlite3')
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.call('GET', '/api/state')

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        code, out = dispatch(self.db, method, path, body or {})
        self.assertEqual(code, 200, out)
        return out

    def csv(self, rows):
        f = io.StringIO()
        writer = csv.DictWriter(f, fieldnames=['type', 'value', 'unit', 'at', 'source'])
        writer.writeheader()
        for kind, value, unit, hours, source in rows:
            writer.writerow(dict(type=kind, value=value, unit=unit,
                                 at=(self.now-timedelta(hours=hours)).isoformat(), source=source))
        return parse_export(f.getvalue().encode('utf-8-sig'), 'my-health.csv')

    def import_csv(self, rows):
        return self.call('POST', '/api/wearable', {'_parsed': self.csv(rows)})

    def task(self):
        return self.call('POST', '/api/tasks', {'input':'今天只有30分钟，没有不适，想调整今天训练'})['activeTask']

    def test_csv_import_persists_real_origin_and_actual_values(self):
        self.import_csv([('resting_hr', 58, 'bpm', 2, 'My Garmin'),
                         ('sleep', 420, 'min', 3, 'Apple Watch'),
                         ('hrv_sdnn', .052, 's', 1, 'Apple Watch')])
        state = self.call('GET', '/api/state')
        d = state['device']
        self.assertFalse(d['simulated'])
        self.assertEqual(d['sourceType'], '健康记录导入')
        self.assertEqual(d['mode'], 'complete')
        self.assertFalse(d['live'])
        self.assertTrue(state['permissions']['device'])
        metrics = {r['key']: r for r in d['metrics']}
        self.assertEqual(metrics['sleep']['value'], '7.0')
        self.assertEqual(metrics['hrv_sdnn']['value'], '52.0')
        self.assertEqual(metrics['resting_hr']['source'], 'My Garmin')
        self.assertEqual(d['sourceNames'], ['Apple Watch', 'My Garmin'])

    def test_older_import_cannot_replace_newer_measurement(self):
        self.import_csv([('resting_hr', 57, 'bpm', 1, 'Watch A')])
        self.import_csv([('resting_hr', 70, 'bpm', 24, 'Watch B'),
                         ('sleep', 6, 'hours', 2, 'Watch B')])
        metrics = {r['key']: r for r in self.call('GET', '/api/state')['device']['metrics']}
        self.assertEqual(metrics['resting_hr']['value'], '57.0')
        self.assertEqual(metrics['resting_hr']['source'], 'Watch A')
        self.assertEqual(metrics['sleep']['value'], '6.0')
        self.import_csv([('resting_hr', 59, 'bpm', .5, 'Watch C')])
        d = self.call('GET', '/api/state')['device']
        self.assertEqual({r['key']:r for r in d['metrics']}['resting_hr']['value'], '59.0')
        self.assertEqual(d['sourceNames'], ['Watch B', 'Watch C'])

    def test_only_fresh_individual_metrics_are_task_evidence(self):
        self.import_csv([('resting_hr', 58, 'bpm', 1, 'Watch current'),
                         ('sleep', 8, 'hours', 48, 'Watch old'),
                         ('hrv_sdnn', 52, 'ms', 72, 'Watch old')])
        device_evidence = [x for x in self.task()['evidence'] if x.get('device')]
        self.assertEqual(len(device_evidence), 1)
        self.assertEqual(device_evidence[0]['label'], '静息心率')
        self.assertEqual(device_evidence[0]['source'], 'Watch current')
        self.assertTrue(any('缺失' in s or '过期' in s for s in self.task()['unknowns']))

    def test_disabling_device_permission_removes_existing_and_future_evidence(self):
        self.import_csv([('resting_hr', 58, 'bpm', 1, 'My Watch')])
        self.assertTrue(any(e.get('device') for e in self.task()['evidence']))
        state = self.call('POST', '/api/settings', {'permissions': {'device':False}})
        self.assertEqual(state['device']['metrics'], [])
        for task in state['history']:
            self.assertFalse(any(e.get('device') for e in task['evidence']))
        self.assertFalse(any(e.get('device') for e in self.task()['evidence']))

    def test_disconnect_does_not_fall_back_to_example_metrics(self):
        self.import_csv([('resting_hr', 58, 'bpm', 1, 'My Watch')])
        state = self.call('POST', '/api/wearable/disconnect')
        self.assertFalse(state['device']['simulated'])
        self.assertEqual(state['device']['metrics'], [])
        self.call('POST', '/api/settings', {'permissions':{'device':True}})
        self.assertFalse(any(e.get('device') for e in self.task()['evidence']))


if __name__ == '__main__':
    unittest.main()
