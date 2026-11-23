import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import http.cookiejar
import io
import socket
from functools import partial
from http.server import ThreadingHTTPServer
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import dispatch,encode
from intent import LocalIntent
from server import PivotHandler
from mobile_backend import Pairing,VideoManager

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.tmp.name)/'test.sqlite')
        self.call('GET','/api/state')
    def tearDown(self):
        self.tmp.cleanup()
    def call(self,method,path,body=None,code=200):
        status,value=dispatch(self.db,method,path,body or {})
        self.assertEqual(status,code,value)
        return value
    def draft(self):
        return self.call('POST','/api/tasks',{'input':'今天只有30分钟，没有不适，今天练'})['activeTask']
    def confirm(self,t,key='confirm_1234'):
        return {'id':t['id'],'draftVersion':t['draftVersion'],'optionId':t['options'][0]['id'],'idempotencyKey':key}
    def session(self,**kw):
        return dict(completion='completed',minutes=20,feeling='合适',discomfort=False,idempotencyKey='session_1234',**kw)
    def test_confirm_replay_lookup_and_conflict(self):
        t=self.draft(); b=self.confirm(t)
        first=self.call('POST','/api/confirm',b)
        again=self.call('POST','/api/confirm',b)
        self.assertEqual(first['plan'],again['plan'])
        self.assertEqual(first['operation'],again['operation'])
        self.assertEqual(first['activeTask']['receipt']['operationId'],first['operation']['operationId'])
        self.assertEqual(first['activeTask']['receipt']['at'],first['operation']['at'])
        for ident in (b['idempotencyKey'],first['operation']['operationId']):
            self.assertEqual(self.call('GET','/api/operations/'+ident)['operation'],first['operation'])
        self.call('POST','/api/confirm',{**b,'remind':True},409)
        self.call('GET','/api/operations/unknown',code=404)

    def test_checked_recovery_reserves_only_the_original_confirm(self):
        task = self.draft()
        request = self.confirm(task,'confirm_recover')
        original = self.call('GET','/api/state')['plan']
        result = self.call('POST','/api/confirm/check',request)['operation']
        self.assertEqual(result,{'status':'not_submitted','taskId':task['id'],'idempotencyKey':'confirm_recover'})
        self.assertEqual(self.call('GET','/api/state')['plan'],original)
        self.call('GET','/api/operations/confirm_recover',code=404)
        wrong = self.call('POST','/api/confirm',{**request,'remind':True},409)
        self.assertEqual(wrong['code'],'idempotency_conflict')
        committed = self.call('POST','/api/confirm',request)
        self.assertEqual(committed['plan']['version'],original['version']+1)
        self.assertEqual(self.call('POST','/api/confirm/check',request)['operation'],committed['operation'])

    def test_check_stale_or_already_completed_task_with_new_key(self):
        task = self.draft()
        request = self.confirm(task)
        result = self.call('POST','/api/confirm',request)
        current = result['plan']
        self.call('POST','/api/plan',{**current,'expectedVersion':current['version'],'minutes':45})
        latest = self.call('GET','/api/state')['plan']
        self.assertEqual(self.call('POST','/api/confirm/check',request)['operation'],result['operation'])
        with_new_key = {**request,'idempotencyKey':'another_confirm'}
        for endpoint in ('/api/confirm','/api/confirm/check'):
            self.assertEqual(self.call('POST',endpoint,with_new_key,409)['code'],'already_confirmed')
        self.call('GET','/api/operations/another_confirm',code=404)
        self.assertEqual(self.call('GET','/api/state')['plan'],latest)
        self.call('POST','/api/alternatives',{'items':[{'title':'我确认的徒手备选','minutes':25,'equipment':'徒手'}]})
        t = self.draft()
        self.call('POST','/api/plan',{**latest,'expectedVersion':latest['version'],'minutes':50})
        stale = self.call('POST','/api/confirm/check',self.confirm(t,'stale_key'),409)
        self.assertEqual(stale['code'],'stale_draft')

    def test_legacy_receipt_number_resolves_original_operation(self):
        task = self.draft()
        result = self.call('POST','/api/confirm',self.confirm(task))
        legacy_receipt_id = 'b'*32
        existing = result['activeTask']
        existing['receipt']['operationId'] = legacy_receipt_id
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE tasks SET data=? WHERE id=?',(encode(existing),task['id']))
        self.assertEqual(self.call('GET','/api/operations/'+legacy_receipt_id)['operation'],result['operation'])

    def test_plan_change_blocks_stale_confirm(self):
        t=self.draft()
        s=self.call('GET','/api/state')
        b={**s['plan'],'expectedVersion':s['plan']['version']}
        b['minutes']=45
        self.call('POST','/api/plan',b)
        self.call('POST','/api/confirm',self.confirm(t),409)
        self.call('POST','/api/plan',b,409)
    def test_alternatives_are_real_candidates_and_invalidate(self):
        t=self.draft()
        self.call('POST','/api/alternatives',{'items':[{'id':'custom','title':'我的15分钟版本','minutes':15}]})
        self.call('POST','/api/confirm',self.confirm(t),409)
        new=self.draft()
        self.assertEqual([x['id'] for x in new['options']],['custom'])
        self.call('POST','/api/alternatives',{'items':[]})
        self.assertEqual(self.draft()['status'],'needs_info')
    def test_reschedule_uses_requested_time_not_sample_calendar(self):
        tomorrow=str(date.today()+timedelta(days=1))
        t=self.call('POST','/api/tasks',{'input':f'请改到{tomorrow}上午9点，没有不适'})['activeTask']
        self.assertEqual(t['status'],'draft',t)
        option=next(x for x in t['options'] if x['id']=='reschedule')
        self.assertEqual((option['date'],option['time']),(tomorrow,'09:00'))
        self.assertTrue(option['requiresAvailabilityConfirmation'])
        self.assertIn('尚未接入日历',option['reason'])
        b=self.confirm(t)
        self.assertEqual(self.call('POST','/api/confirm',b,400)['code'],'availability_confirmation_required')
        self.call('POST','/api/confirm',{**b,'availabilityConfirmed':True})
    def test_connected_symptom_negation(self):
        from engine import safety
        for text in ('没有疼痛或不适','没有疼痛也没有不适','无疼痛不适','没有头晕、胸闷、疼痛','没有疼痛或明显不适'):
            self.assertFalse(safety(text),text)
            task=self.call('POST','/api/tasks',{'input':'今天只有30分钟，'+text})['activeTask']
            self.assertEqual(task['status'],'draft',text)
        for text in ('没有疼痛或不适，但是胸闷','没有头晕，但膝盖疼痛','不是没有疼痛','没有疼痛，不舒服'):
            self.assertTrue(safety(text),text)
    def test_permission_disallows_write(self):
        t=self.draft()
        self.call('POST','/api/settings',{'permissions':{'save':False}})
        self.call('POST','/api/confirm',self.confirm(t),403)
    def test_actual_feedback_cited_and_invalidates(self):
        old=self.draft()
        first=self.call('POST','/api/sessions',self.session())
        again=self.call('POST','/api/sessions',self.session())
        self.assertEqual(len(again['sessions']),1)
        self.assertEqual(first['savedSessionId'],again['savedSessionId'])
        self.call('POST','/api/confirm',self.confirm(old),409)
        new=self.draft()
        evidence=[e for e in new['evidence'] if e['label']=='实际训练反馈']
        self.assertEqual(evidence[0]['sessionId'],first['savedSessionId'])
        sid=first['savedSessionId']
        b={**self.session(),'id':sid,'expectedRevision':1,'minutes':22}
        changed=self.call('POST','/api/sessions/update',b)
        self.assertEqual(changed['sessions'][0]['revision'],2)
        self.call('POST','/api/sessions/update',b,409)
        self.call('DELETE','/api/sessions/'+sid)
        self.assertFalse(any(e['label']=='实际训练反馈' for e in self.draft()['evidence']))
    def test_video_correction_preserves_model_and_delete_history(self):
        ident='a'*32
        result={'count':4,'quality':'usable','validRatio':.9,'side':'left','sourceUrl':'/media/'+ident+'.mp4','modelVersion':'test','ruleVersion':'test'}
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO video_jobs VALUES(?,?)',(ident,encode({'jobId':ident,'status':'done','result':result})))
        b=self.session(videoJobId=ident,correctedCount=5)
        self.call('POST','/api/sessions',b,400)
        b['correctionReason']='完整动作人工回看为5次'
        state=self.call('POST','/api/sessions',b)
        obs=state['sessions'][0]['observation']
        self.assertEqual((obs['originalCount'],obs['confirmedCount']),(4,5))
        v=VideoManager(self.db); v.delete(ident)
        final=self.call('GET','/api/state')
        self.assertNotIn('sourceUrl',final['sessions'][0]['observation'])
        self.assertEqual(final['sessions'][0]['observation']['confirmedCount'],5)
        self.assertEqual(final['videoJobs'],[])
        v.pool.shutdown()
    def test_expiry_retains_observation_and_restart_marks_interrupted(self):
        from datetime import datetime
        ident='d'*32
        created=(datetime.now().astimezone()-timedelta(days=8)).isoformat()
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO video_jobs VALUES(?,?)',(ident,encode({'jobId':ident,'status':'done','createdAt':created,
                'result':{'count':4,'quality':'usable','sourceUrl':'/media/'+ident+'.mp4'}})))
            db.execute('INSERT INTO video_jobs VALUES(?,?)',('e'*32,encode({'jobId':'e'*32,'status':'running'})))
        self.call('POST','/api/sessions',self.session(videoJobId=ident))
        folder=Path(self.db).with_suffix('.assets')/'media';folder.mkdir(parents=True)
        (folder/(ident+'.mp4')).write_bytes(b'private')
        v=VideoManager(self.db)
        state=self.call('GET','/api/state')
        self.assertFalse((folder/(ident+'.mp4')).exists())
        self.assertEqual(state['sessions'][0]['observation']['originalCount'],4)
        self.assertNotIn('sourceUrl',state['sessions'][0]['observation'])
        self.assertEqual(v.get('e'*32)['status'],'error')
        v.pool.shutdown()
    def test_draft_expiry(self):
        t=self.draft()
        with sqlite3.connect(self.db) as db:
            t['expiresAt']='2000-01-01T00:00:00+00:00'
            db.execute('UPDATE tasks SET data=? WHERE id=?',(encode(t),t['id']))
        response=self.call('POST','/api/confirm',self.confirm(t),409)
        self.assertEqual(response['code'],'draft_expired')
    def test_insufficient_is_unknown(self):
        ident='b'*32
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO video_jobs VALUES(?,?)',(ident,encode({'jobId':ident,'status':'done','result':{'count':None,'quality':'insufficient'}})))
        state=self.call('POST','/api/sessions',self.session(videoJobId=ident))
        self.assertIsNone(state['sessions'][0]['observation']['confirmedCount'])
    def test_session_validation(self):
        for change in ({'completion':'not_done'},{'minutes':0},{'feeling':'假的'},{'discomfort':'false'},
                       {'performedAt':str(date.today()+timedelta(days=1))},{'taskId':'missing'}):
            expected=404 if 'taskId' in change else 400
            self.call('POST','/api/sessions',{**self.session(),**change},expected)
    def test_session_weight_is_validated_without_server_error(self):
        for weight in ('abc',None,[],{},True,'nan','inf',-1,501):
            with self.subTest(weight=weight):
                self.call('POST','/api/sessions',{**self.session(),'weight':weight},400)
        self.assertEqual(self.call('GET','/api/state')['sessions'],[])
        state=self.call('POST','/api/sessions',{**self.session(),'weight':'12.5'})
        self.assertEqual(state['sessions'][0]['weight'],12.5)
    def test_plan_and_alternative_content_survives_legacy_edits(self):
        plan=self.call('GET','/api/state')['plan']
        first=self.call('POST','/api/plan',{**plan,'expectedVersion':plan['version'],
            'purpose':'维持力量训练习惯','content':'深蹲 3组×8次；划船 3组×10次','equipment':'哑铃'})
        plan=first['plan']
        old_client={k:v for k,v in plan.items() if k not in ('purpose','content','equipment')}
        changed=self.call('POST','/api/plan',{**old_client,'expectedVersion':plan['version'],'minutes':25})
        self.assertEqual(changed['plan']['content'],'深蹲 3组×8次；划船 3组×10次')
        self.assertEqual(changed['plan']['purpose'],'维持力量训练习惯')
        state=self.call('POST','/api/alternatives',{'items':[{'id':'own','title':'短时力量','minutes':20,
            'purpose':'维持训练','content':'分腿蹲 2组×8次','equipment':'自重','intensity':'light'}]})
        state=self.call('POST','/api/alternatives',{'items':[{'id':'own','title':'短时力量改名','minutes':15}]})
        self.assertEqual(state['alternatives'][0]['content'],'分腿蹲 2组×8次')
        self.assertEqual(state['alternatives'][0]['equipment'],'自重')
        self.assertEqual(state['alternatives'][0]['intensity'],'light')
        self.call('POST','/api/alternatives',{'items':[{'id':'own','title':'bad','minutes':20,'intensity':'unverified'}]},400)
        for key,limit in (('purpose',120),('content',1500),('equipment',200)):
            self.call('POST','/api/alternatives',{'items':[{'id':'own','title':'bad','minutes':20,key:'x'*(limit+1)}]},400)
    def test_old_db_migration_preserves_plan(self):
        with sqlite3.connect(self.db) as db:
            ctx=json.loads(db.execute('SELECT data FROM workspace').fetchone()[0]);ctx['pristine']=False
            ctx['plan']['title']='旧有用户计划'
            for k in ('alternatives','weeklyGoal','recentSessions'):ctx.pop(k,None)
            db.execute('UPDATE workspace SET data=?',(encode(ctx),))
        state=self.call('GET','/api/state')
        self.assertEqual(state['plan']['title'],'旧有用户计划')
        self.assertIn('sessions',state)
    def test_onboarding_does_not_invent_user_activity_or_device(self):
        state=self.call('GET','/api/state')
        self.assertFalse(state['permissions']['device'])
        self.assertEqual(state['device']['metrics'],[])
        self.assertTrue(state['planIsExample'])
        self.assertFalse(state['profileConfirmed'])
        t=self.draft()
        self.assertFalse(any(e['label']=='最近运动' for e in t['evidence']))
        self.assertFalse(any(e.get('device') for e in t['evidence']))
        state=self.call('POST','/api/settings',{'profile':{'goal':'每周三次训练'}})
        self.assertTrue(state['profileConfirmed'])
        self.assertEqual(state['profile']['goal'],'每周三次训练')
    def test_partial_upload_releases_lock_and_files(self):
        v=VideoManager(self.db)
        v.info=lambda:{'available':True}
        from engine import RequestError
        with self.assertRaises(RequestError) as failure:
            v.upload(io.BytesIO(b'partial'),100,'left')
        self.assertEqual(failure.exception.code,'upload_incomplete')
        self.assertFalse(v.lock.locked())
        self.assertEqual(list(v.media.iterdir()),[])
        with self.assertRaises(RequestError) as failure:
            v.upload(io.BytesIO(b''),60*1024*1024+1,'left')
        self.assertEqual(failure.exception.status,413)
        with self.assertRaises(RequestError):v.upload(io.BytesIO(b''),1,'invalid')
        v.pool.shutdown()
    def test_relative_database_uses_absolute_media_paths_for_subprocess(self):
        v=VideoManager(os.path.relpath(self.db))
        try:
            self.assertEqual(v.db_path,str(Path(self.db).resolve()))
            self.assertTrue(v.media.is_absolute())
            self.assertTrue(v.jobs.is_absolute())
            self.assertTrue(v.media.is_dir())
        finally:v.pool.shutdown()
    def test_server_events_are_real_idempotent_and_private(self):
        private_text='今天只剩30分钟，没有不适，私人测试备注'
        t=self.call('POST','/api/tasks',{'input':private_text})['activeTask']
        event={'eventId':'draft_event_12345','event':'draft_view','taskId':t['id'],'draftVersion':t['draftVersion']}
        first=self.call('POST','/api/events',event)
        self.assertEqual(self.call('POST','/api/events',event),first)
        self.call('POST','/api/events',{**event,'text':private_text},400)
        b=self.confirm(t);self.call('POST','/api/confirm',b);self.call('POST','/api/confirm',b)
        self.call('POST','/api/sessions',self.session())
        self.call('POST','/api/sessions',self.session())
        events=self.call('GET','/api/export')['events']
        names=[e['event'] for e in events]
        for name in ('adjust_start','draft_view','plan_confirm','operation_finished','training_recorded'):
            self.assertEqual(names.count(name),1,(name,names))
        self.assertNotIn(private_text,json.dumps(events,ensure_ascii=False))
    def test_pristine_old_database_never_auto_resets(self):
        with sqlite3.connect(self.db) as db:
            data=json.loads(db.execute('SELECT data FROM workspace').fetchone()[0])
            data['sampleDay']='2020-01-01';data['pristine']=True;data['plan']['title']='必须保留'
            db.execute('UPDATE workspace SET data=?',(encode(data),))
        self.assertEqual(self.call('GET','/api/state')['plan']['title'],'必须保留')
    def test_weekly_goal_and_export(self):
        self.call('POST','/api/settings',{'weeklyGoal':8},400)
        self.assertEqual(self.call('POST','/api/settings',{'weeklyGoal':4})['weeklyGoal'],4)
        self.assertIn('exportedAt',self.call('GET','/api/export'))
    def test_discomfort_stops_adjustment(self):
        state=self.call('POST','/api/tasks',{'input':'今天膝盖疼痛，只有30分钟'})
        self.assertEqual(state['activeTask']['status'],'stopped')

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.db=Path(cls.tmp.name)/'http.sqlite'
        dispatch(str(cls.db),'GET','/api/state',{})
        cls.video=VideoManager(cls.db)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),partial(PivotHandler,db_path=str(cls.db),video=cls.video,
            model=LocalIntent(enabled=False),pairing=Pairing('test-code-123')))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.video.pool.shutdown();cls.tmp.cleanup()
    def setUp(self):
        self.cookies=http.cookiejar.CookieJar()
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
    def request(self,path,method='GET',body=None,headers=None,code=200):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.url+path,data=data,method=method,headers={'Content-Type':'application/json',**(headers or {})})
        try:resp=self.client.open(req,timeout=10)
        except urllib.error.HTTPError as e:resp=e
        content=resp.read();self.assertEqual(resp.status,code,content)
        return resp,content
    def pair(self):self.request('/api/auth/pair','POST',{'code':'test-code-123'})
    def test_auth_access_cookie_logout(self):
        self.request('/api/state',code=401)
        self.request('/api/auth/pair','POST',{'code':'wrong'},code=401)
        r,_=self.request('/api/auth/pair','POST',{'code':'test-code-123'})
        self.assertIn('HttpOnly',r.headers['Set-Cookie']);self.assertIn('SameSite=Strict',r.headers['Set-Cookie'])
        self.request('/api/state')
        self.request('/api/auth/logout','POST',{})
        self.request('/api/state',code=401)
    def test_host_and_origin_denied(self):
        self.request('/api/health',headers={'Host':'evil.example'},code=403)
        self.pair()
        self.request('/api/settings','POST',{'weeklyGoal':3},headers={'Origin':'https://evil.example'},code=403)
    def test_upload_requires_auth_and_type(self):
        self.request('/api/video','POST',{},code=401)
        self.pair();self.request('/api/video','POST',{},code=415)
    def test_error_format_preserves_existing_clients(self):
        header='X-Pivot-Error-Format'
        response,legacy=self.request('/api/state',code=401)
        legacy=json.loads(legacy)
        self.assertEqual(legacy,{'code':'pair_required','error':'请先输入配对码连接你的 Pivot。'})
        self.assertEqual(response.headers['Vary'],header)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        response,structured=self.request('/api/state',headers={header:'structured'},code=401)
        self.assertEqual(json.loads(structured),{'error':{'code':legacy['code'],'message':legacy['error']}})
        self.assertEqual(response.headers['Vary'],header)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        _,explicit_legacy=self.request('/api/state',headers={header:'legacy'},code=401)
        self.assertEqual(json.loads(explicit_legacy),legacy)
        _,old_success=self.request('/api/health')
        _,new_success=self.request('/api/health',headers={header:'structured'})
        self.assertEqual(json.loads(old_success),json.loads(new_success))

    def test_structured_errors_include_dispatch_and_upload_failures(self):
        self.pair()
        headers={'X-Pivot-Error-Format':'structured'}
        cases=[
            ('GET','/api/operations/missing_op',None,404,'not_found'),
            ('POST','/api/video',{},415,'unsupported_type'),
            ('POST','/api/wearable/import','not-a-health-export',422,'bad_health_file'),
            ('PUT','/api/tasks',{},501,'method_not_allowed'),
        ]
        for method,path,body,status,error_code in cases:
            with self.subTest(path=path):
                response,raw=self.request(path,method,body,headers=headers,code=status)
                self.assertEqual(response.headers.get_content_type(),'application/json')
                payload=json.loads(raw)
                self.assertEqual(set(payload),{'error'})
                self.assertEqual(set(payload['error']),{'code','message'})
                self.assertEqual(payload['error']['code'],error_code)
                self.assertTrue(payload['error']['message'])
    def test_media_range_and_private(self):
        ident='c'*32
        raw=bytes(range(128))
        (self.video.media/(ident+'.mp4')).write_bytes(raw)
        with self.video.database() as db:
            db.execute('INSERT OR REPLACE INTO video_jobs VALUES(?,?)',(ident,encode({'jobId':ident,'status':'done'})))
        path='/media/'+ident+'.mp4'
        self.request(path,code=401);self.pair()
        r,data=self.request(path,headers={'Range':'bytes=10-19'},code=206)
        self.assertEqual(data,raw[10:20]);self.assertEqual(r.headers['Content-Range'],'bytes 10-19/128')
        _,data=self.request(path,headers={'Range':'bytes=-5'},code=206);self.assertEqual(data,raw[-5:])
        self.request(path,headers={'Range':'bytes=500-'},code=416)
        r,data=self.request(path,method='HEAD');self.assertEqual(data,b'');self.assertEqual(r.headers['Content-Length'],'128')
    def test_private_export_and_traversal(self):
        self.request('/api/export',code=401)
        self.request('/media/'+'f'*32+'.mp4',code=401)
        for path in ('/../engine.py','/%2e%2e/server.py','/server.py','/../../../../etc/passwd'):
            self.request(path,code=404)
    def test_malformed_json_content_length_and_pair_limit(self):
        req=urllib.request.Request(self.url+'/api/auth/pair',data=b'{bad',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:self.client.open(req)
        self.assertEqual(error.exception.code,400)
        req=urllib.request.Request(self.url+'/api/auth/pair',data=b'{}',headers={'Content-Type':'application/json','Content-Length':'nonsense'})
        with self.assertRaises(urllib.error.HTTPError) as error:self.client.open(req)
        self.assertEqual(error.exception.code,413)
        req=urllib.request.Request(self.url+'/api/auth/pair',data=b'[]',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:self.client.open(req)
        self.assertEqual(error.exception.code,400)
        from engine import RequestError
        pairing=Pairing('test-code-long')
        for i in range(10):
            with self.assertRaises(RequestError) as error:pairing.pair('wrong','test-peer')
            self.assertEqual(error.exception.status,401)
        with self.assertRaises(RequestError) as error:pairing.pair('test-code-long','test-peer')
        self.assertEqual(error.exception.status,429)
    def test_network_config_requires_pairing(self):
        with self.assertRaises(ValueError):Pairing('short','')
        with self.assertRaises(ValueError):Pairing('','https://example.com')
        with self.assertRaises(ValueError):Pairing('long-code','http://example.com')

if __name__=='__main__':unittest.main()
