"""Run against a loopback V1.1.3 preview using new synthetic guest spaces."""
import argparse
from http.cookiejar import CookieJar
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


class Guest:
    def __init__(self, origin):
        self.origin = origin.rstrip('/')
        self.http = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, path, payload=None, expected=200):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = Request(f'{self.origin}/api/{path}', body, {'Content-Type': 'application/json'})
        try:
            response = self.http.open(request, timeout=35)
        except HTTPError as error:
            response = error
        with response:
            status, data = response.code, json.load(response)
        assert status == expected, (path, status, data)
        return data


def form_for(plan, template, actions=None):
    return {
        'expectedVersion': plan['version'], 'title': template['title'],
        'date': plan['date'], 'time': plan['time'], 'minutes': template['minutes'],
        'purpose': template['purpose'], 'templateId': template['id'],
        'actions': template['actions'] if actions is None else actions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8897')
    args = parser.parse_args()
    url = urlsplit(args.origin)
    assert url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')
    guest = Guest(args.origin)
    health = guest.request('health')
    assert health['demoVersion'] == '1.1.3'
    state = guest.request('state')
    catalog = state['trainingCatalog']
    assert catalog['preview'] and catalog['reviewStatus'] == 'pending'
    exercises = {item['id']: item for item in catalog['exercises']}
    assert 50 <= len(exercises) <= 60
    assert len(exercises) == len(catalog['exercises'])
    assert len({item['category'] for item in exercises.values()}) == 8
    assert {key for key, item in exercises.items() if item['videoSupported']} == set(health['vision']['actions'])
    templates = {item['id']: item for item in catalog['templates']}
    assert {t['title'] for t in templates.values()} == {'居家弹力带全身', '健身房下肢与躯干', '球场脚步与制动'}

    fields = {
        'reps': {'sets': 2, 'reps': 8, 'weight': 0},
        'time': {'seconds': 15},
        'distance': {'distanceMeters': 10, 'seconds': 5},
        'rounds': {'rounds': 2, 'seconds': 30},
    }
    for template in templates.values():
        guest = Guest(args.origin)
        state = guest.request('state')
        original = template['actions']
        reordered = [*original[1:], original[0]]
        plan = guest.request('plan', form_for(state['plan'], template, reordered))['plan']
        assert plan['version'] == state['plan']['version'] + 1
        ids = [item['exerciseId'] for item in reordered]
        assert [item['exerciseId'] for item in plan['actions']] == ids
        for metric in fields:
            exercise = next(item for item in exercises.values() if item['metric'] == metric)
            if exercise['id'] not in ids:
                ids.append(exercise['id'])
        entries = [{'exerciseId': key, **fields[exercises[key]['metric']]} for key in ids]
        payload = {'completion': 'completed', 'minutes': plan['minutes'], 'feeling': '合适',
                   'discomfort': False, 'exerciseEntries': entries, 'idempotencyKey': uuid4().hex}
        recorded = guest.request('sessions', payload)
        repeated = guest.request('sessions', payload)
        assert recorded['operation'] == repeated['operation']
        saved = next(item for item in guest.request('state')['sessions'] if item['id'] == recorded['savedSessionId'])
        assert [item['exerciseId'] for item in saved['exerciseEntries']] == ids
        for entry, submitted in zip(saved['exerciseEntries'], entries):
            assert entry['metric'] == exercises[entry['exerciseId']]['metric']
            assert entry['exerciseName'] == exercises[entry['exerciseId']]['name']
            assert all(entry[key] == value for key, value in submitted.items()), (entry, submitted)
        print(f'Template and multi-action log passed: {template["title"]}')

    gym = templates['gym_lower_body_core']
    guest = Guest(args.origin)
    plan = guest.request('plan', form_for(guest.request('state')['plan'], gym))['plan']
    text = '今晚临时约了球，今天只有30分钟，家里只有弹力带，状态正常。'
    response = guest.request('tasks', {'input': text})
    task = response['activeTask']
    assert task['status'] == 'needs_info' and '固定' in task['question'], task
    assert response['plan']['version'] == plan['version']
    response = guest.request('answer', {'id': task['id'], 'text': '确认有合适的弹力带固定点。'})
    task = response['activeTask']
    assert task['status'] == 'draft' and response['plan']['version'] == plan['version'], task
    candidate = next(item for item in task['options'] if any(
        row['exerciseId'] == 'band_row' for row in item.get('actions', [])))
    assert candidate['minutes'] <= 30 and '哑铃划船' in json.dumps(candidate, ensure_ascii=False)
    assert '球' in candidate['changes']['ballImpact']
    payload = {'id': task['id'], 'optionId': candidate['id'], 'draftVersion': task['draftVersion'],
               'availabilityConfirmed': True, 'idempotencyKey': uuid4().hex}
    saved = guest.request('confirm', payload)
    assert saved['plan']['version'] == plan['version'] + 1
    assert saved['plan']['actions'] == candidate['actions']
    assert saved['operation'] == guest.request('confirm', payload)['operation']
    assert saved['operation'] == guest.request('operations/' + saved['operation']['operationId'])['operation']
    assert guest.request('state')['plan']['actions'] == candidate['actions']
    print('Agent short plan passed: prerequisite question, action diff, confirmed write, and receipt lookup')
    print('Interpretation source:', task.get('interpretation', {}).get('source', 'unknown'))


if __name__ == '__main__':
    main()
