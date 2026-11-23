import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import dispatch
from experience import initialize


class DecisionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / 'decisions.sqlite3')
        self.call('GET', '/api/state')
        with sqlite3.connect(self.db) as connection:
            initialize(connection)

    def call(self, method, path, body=None):
        status, data = dispatch(self.db, method, path, body or {})
        self.assertEqual(status, 200, data)
        return data

    def request(self, text, **context):
        return self.call('POST', '/api/tasks', {'input': text, 'context': context})['activeTask']

    def answer(self, task, text):
        return self.call('POST', '/api/answer', {'id': task['id'], 'text': text})['activeTask']

    @staticmethod
    def options(task):
        return [candidate['id'] for candidate in task['options']]

    def test_equipment_changes_candidates_for_the_same_plan_and_time(self):
        dumbbell = self.request('今天只有 30 分钟', scenario='short', minutes=30, equipment='哑铃', condition='normal')
        band = self.request('今天只有 30 分钟，只有弹力带，状态正常')
        self.assertEqual(dumbbell['original'], band['original'])
        self.assertEqual(dumbbell['original']['minutes'], 60)
        self.assertEqual(self.options(dumbbell), ['short', 'routine_20', 'light'])
        self.assertEqual(self.options(band), ['band', 'routine_20', 'light'])
        self.assertTrue(any('哑铃' in item['reason'] for item in band['excludedCandidates']))
        self.assertIn('周末篮球', band['options'][0]['changes']['ballImpact'])
        for item in band['options']:
            self.assertIn('示例备选', item['source'])

    def test_restriction_and_goal_are_not_ignored(self):
        restricted = self.request('今天只有30分钟，只有弹力带，不能做上肢推拉，状态正常')
        self.assertNotIn('band', self.options(restricted))
        self.assertEqual(next(x for x in restricted['excludedCandidates'] if '弹力带力量' in x['title'])['code'], 'restriction')
        self.call('POST', '/api/alternatives', {'items': [
            {'id': 'upper', 'title': '上肢训练', 'minutes': 20, 'content': '上肢动作'},
            {'id': 'core', 'title': '核心练习', 'minutes': 20, 'content': '个人核心计划'},
        ]})
        self.call('POST', '/api/settings', {'profile': {'goal': '保持核心训练'}})
        goal = self.request('今天只有 30 分钟，状态正常')
        self.assertEqual(self.options(goal), ['core'])

    def test_only_pivotal_equipment_is_asked_and_can_be_left_unknown(self):
        draft = self.request('今天只有30分钟，状态正常')
        self.assertEqual(draft['status'],'needs_info')
        self.assertIn('哪些器械', draft['question'])
        without_known_equipment = self.answer(draft, '器械未知')
        self.assertEqual(self.options(without_known_equipment), ['routine_20', 'light'])

    def test_reschedule_asks_for_the_new_slot_and_reveals_same_day_uncertainty(self):
        draft = self.request('今晚临时约了球，状态正常')
        self.assertEqual(draft['status'], 'needs_info')
        self.assertIn('哪一天、几点', draft['question'])
        event = self.call('GET', '/api/state')['goalContext']['eventDate']
        draft = self.answer(draft, event)
        self.assertIn('几点', draft['question'])
        draft = self.answer(draft, '19:00')
        self.assertEqual(self.options(draft), ['reschedule'])
        option = draft['options'][0]
        self.assertEqual((option['date'], option['time']), (event, '19:00'))
        self.assertTrue(option['requiresAvailabilityConfirmation'])
        self.assertIn('同日是否冲突', option['changes']['ballImpact'])

    def test_sleep_change_is_independent_of_today_and_discomfort_stops(self):
        draft = self.request('昨晚没睡好，今天状态正常，只有30分钟，只有弹力带')
        self.assertEqual(self.options(draft), ['band','routine_20','light'])
        self.assertTrue(any(item['label']=='睡眠变化' for item in draft['evidence']))
        self.assertEqual(draft['requestContext']['condition'], 'normal')
        stopped = self.request('今天只有30分钟，现在明显不适')
        self.assertEqual((stopped['status'], stopped['options']), ('stopped', []))

    def test_partial_tired_feedback_changes_the_next_question_and_qualification(self):
        first = self.request('今天只有 30 分钟', scenario='short', minutes=30, equipment='弹力带', condition='normal')
        self.call('POST', '/api/confirm', {'id': first['id'], 'optionId': 'band', 'draftVersion': first['draftVersion'], 'idempotencyKey': 'accept_confirm_band'})
        before = self.request('今天有20分钟', scenario='short', minutes=20, condition='unknown')
        self.assertNotIn('上一次', before['question'])
        saved = self.call('POST', '/api/sessions', {'taskId':first['id'],'completion':'partial','minutes':20,
            'feeling':'偏累','discomfort':False,'idempotencyKey':'accept_partial_feedback'})
        self.assertTrue(saved['sessions'][0]['example'])
        second = self.request('今天有20分钟', scenario='short', minutes=20, condition='unknown')
        self.assertIn('上一次部分完成 20 分钟并记录偏累', second['question'])
        normal = self.answer(second, '今天状态正常')
        self.assertEqual(self.options(normal), ['routine_20','light'])
        another = self.request('今天有20分钟', scenario='short', minutes=20, condition='unknown')
        tired = self.answer(another, '今天仍有些疲劳')
        self.assertEqual(self.options(tired), ['light'])
        self.assertEqual(tired['requestContext']['condition'], 'tired')


if __name__=='__main__':
    unittest.main()
