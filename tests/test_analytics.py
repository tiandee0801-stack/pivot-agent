"""Events stay minimal, idempotent and inside the existing transaction."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analytics
from engine import RequestError


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        self.task_id = 'a' * 32
        self.db.execute('INSERT INTO tasks VALUES(?,?)', (self.task_id, json.dumps({'id':self.task_id, 'draftVersion':2})))
        analytics.initialize(self.db)
        self.db.commit()
        self.body = {'eventId':'b' * 32, 'event':'draft_view', 'taskId':self.task_id, 'draftVersion':2}

    def tearDown(self):
        self.db.close()

    def test_server_allowlist_never_stores_raw_text_or_nested_payload(self):
        event = analytics.record(self.db, 'adjust_start', {
            'taskId':self.task_id, 'scenario':'shorten', 'round':0,
            'text':'private utterance', 'code':'secret', 'note':'sensitive',
            'profile':{'goal':'private'}, 'apiKey':'secret'})
        self.assertEqual(set(event), {'eventId','event','createdAt','source','taskId','scenario','round'})
        self.assertNotIn('private', json.dumps(analytics.list_events(self.db)))
        self.assertEqual(event['source'], 'server')

    def test_all_server_names_are_supported(self):
        for name in analytics.SERVER_EVENTS:
            self.assertEqual(analytics.record(self.db, name, {})['event'], name)
        self.assertEqual(len(analytics.list_events(self.db)), len(analytics.SERVER_EVENTS))

    def test_frontend_cannot_spoof_execution_event(self):
        with self.assertRaises(RequestError):
            analytics.ingest(self.db, dict(self.body, event='operation_finished'))
        self.assertEqual(analytics.list_events(self.db), [])

    def test_frontend_rejects_extra_fields(self):
        with self.assertRaises(RequestError):
            analytics.ingest(self.db, dict(self.body, note='private'))
        self.assertEqual(analytics.list_events(self.db), [])

    def test_frontend_same_payload_retries_return_original(self):
        original = analytics.ingest(self.db, self.body)
        self.assertEqual(analytics.ingest(self.db, self.body), original)
        self.assertEqual(len(analytics.list_events(self.db)), 1)

    def test_same_id_different_payload_is_409(self):
        analytics.ingest(self.db, self.body)
        with self.assertRaises(RequestError) as caught:
            analytics.ingest(self.db, dict(self.body, draftVersion=3))
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, 'event_conflict')

    def test_original_retry_survives_task_version_change(self):
        original = analytics.ingest(self.db, self.body)
        self.db.execute('UPDATE tasks SET data=? WHERE id=?', (json.dumps({'draftVersion':3}),self.task_id))
        self.assertEqual(analytics.ingest(self.db,self.body), original)

    def test_new_event_must_match_current_task_version(self):
        with self.assertRaises(RequestError) as caught:
            analytics.ingest(self.db,dict(self.body,draftVersion=1))
        self.assertEqual(caught.exception.status,409)

    def test_missing_task_is_404(self):
        with self.assertRaises(RequestError) as caught:
            analytics.ingest(self.db,dict(self.body,taskId='c'*32))
        self.assertEqual(caught.exception.status,404)

    def test_invalid_numbers_enums_and_nested_values_rejected(self):
        for fields in ({'round':True},{'latencyMs':float('nan')},{'durationSeconds':-1},
                       {'corrected':1},{'taskId':{'text':'secret'}},{'quality':'arbitrary user text'},
                       {'reasonCode':'user said something private'}):
            with self.subTest(fields=fields), self.assertRaises(RequestError):
                analytics.record(self.db,'video_finished',fields)
        self.assertEqual(analytics.list_events(self.db),[])

    def test_record_idempotency_and_source_collision(self):
        original=analytics.record(self.db,'video_submitted',{'jobId':'c'*32},event_id='d'*32)
        self.assertEqual(analytics.record(self.db,'video_submitted',{'jobId':'c'*32},event_id='d'*32),original)
        with self.assertRaises(RequestError) as caught:
            analytics.record(self.db,'video_submitted',{'jobId':'e'*32},event_id='d'*32)
        self.assertEqual(caught.exception.status,409)

    def test_does_not_commit_caller_transaction(self):
        analytics.record(self.db,'adjust_start',{'taskId':self.task_id})
        self.db.rollback()
        self.assertEqual(analytics.list_events(self.db),[])

    def test_event_id_and_missing_field_validation(self):
        for body in (dict(self.body,eventId='short'),dict(self.body,draftVersion=0),
                     dict(self.body,draftVersion=None),dict(self.body,taskId=None),
                     {k:v for k,v in self.body.items() if k!='eventId'}):
            with self.subTest(body=body),self.assertRaises(RequestError):
                analytics.ingest(self.db,body)


if __name__ == '__main__':
    unittest.main()
