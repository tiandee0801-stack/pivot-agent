"""Opt-in real-model end-to-end check. Private input stays in temporary test storage."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from functools import partial
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import dispatch
from guest_spaces import GuestSpaces
from intent import LocalIntent
from server import PivotHandler
from mobile_backend import VideoManager,Pairing

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--guest', action='store_true', help='Use two isolated guest spaces and verify cross-guest media denial.')
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pivot-http-real-') as temp:
        db=Path(temp)/'test.sqlite'
        dispatch(str(db),'GET','/api/state',{})
        video=VideoManager(db)
        pairing=GuestSpaces(Path(temp)/'guest-spaces') if args.guest else Pairing('test-private-pairing')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(PivotHandler,db_path=str(db),video=video,model=LocalIntent(enabled=False),pairing=pairing))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url='http://127.0.0.1:'+str(server.server_port)
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,body=None,method=None,raw=False,headers=None):
            data=body if raw else json.dumps(body).encode() if body is not None else None
            req=urllib.request.Request(url+path,data=data,method=method or ('POST' if data is not None else 'GET'),headers={'Content-Type':'video/mp4' if raw else 'application/json',**(headers or {})})
            with client.open(req,timeout=60) as r:
                content=r.read();return r.status,content if raw and r.headers.get_content_type()!='application/json' else json.loads(content)
        report={'checks':[]}
        try:
            if args.guest:
                call('/api/state')
            else:
                call('/api/auth/pair',{'code':'test-private-pairing'})
            status,uploaded=call('/api/video?side=left',args.input.read_bytes(),raw=True)
            assert status==202
            ident=uploaded['jobId'];began=time.monotonic()
            while True:
                _,job=call('/api/jobs/'+ident)
                if job['status'] in ('done','error'):break
                assert time.monotonic()-began<300
                time.sleep(1)
            assert job['status']=='done',job
            result=job['result'];assert result['quality']=='usable' and type(result['count']) is int,result
            report.update(quality=result['quality'],count=result['count'],validRatio=result['validRatio'],cycleDurationSeconds=result.get('cycleDurationSeconds'),analysisSeconds=round(time.monotonic()-began,2))
            report['checks'].append('real upload -> normalize -> ONNX inference -> full frames result')
            status,media=call(result['sourceUrl'],method='GET',raw=True,headers={'Range':'bytes=0-1023'})
            assert status==206 and len(media)==1024
            report['checks'].append('authenticated video playback Range 206')
            if args.guest:
                outsider=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                with outsider.open(url+'/api/state',timeout=5) as response:
                    assert json.load(response)['videoJobs']==[]
                for private_path in ('/api/jobs/'+ident, result['sourceUrl']):
                    try:
                        outsider.open(url+private_path,timeout=5).close()
                    except urllib.error.HTTPError as exc:
                        assert exc.code==404
                    else:
                        raise AssertionError('Another guest could access a private video or job')
                report['checks'].append('independent guest cannot read actual video or job by known ID')
            b={'videoJobId':ident,'completion':'completed','minutes':20,'feeling':'偏累','discomfort':False,
               'correctedCount':result['count']+1,'correctionReason':'HTTP integration correction exercise','idempotencyKey':'http_session_12345'}
            _,state=call('/api/sessions',b);sid=state['savedSessionId']
            _,again=call('/api/sessions',b);assert len(again['sessions'])==1
            observation=state['sessions'][0]['observation'];assert observation['originalCount']==result['count'];assert observation['confirmedCount']==result['count']+1
            report['checks'].append('corrected count preserves original; idempotent save creates one record')
            request='今天只剩30分钟，只有弹力带，今天状态正常，没有明显不适。' if args.guest else '今天只剩30分钟，没有不适，今天练'
            _,state=call('/api/tasks',{'input':request})
            evidence=[e for e in state['activeTask']['evidence'] if e.get('sessionId')==sid]
            assert evidence and str(result['count']+1) in evidence[0]['value']
            t=state['activeTask'];assert t['status']=='draft'
            b={'id':t['id'],'draftVersion':t['draftVersion'],'optionId':t['options'][0]['id'],'idempotencyKey':'http_confirm_12345'}
            _,state=call('/api/confirm',b);_,lookup=call('/api/operations/'+b['idempotencyKey'])
            assert lookup['operation']==state['operation']
            report['checks'].append('actual video/session feedback cited by next adjustment and confirmed plan lookup')
            _,state=call('/api/jobs/'+ident,method='DELETE')
            assert not state['videoJobs'];assert 'sourceUrl' not in state['sessions'][0]['observation']
            report['checks'].append('delete video removes media link and preserves structured observation')
            _,bad=call('/api/video?side=left',b'not-a-video',raw=True)
            for _ in range(30):
                _,job=call('/api/jobs/'+bad['jobId'])
                if job['status'] in ('done','error'):break
                time.sleep(.2)
            assert job['status']=='error' and not job.get('result'),job
            report['checks'].append('undecodable upload returns error, no fabricated result')
            report['passed']=True
            args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            server.shutdown();server.server_close();video.pool.shutdown()
            if args.guest:
                for _, guest_video in pairing.managers.values():
                    guest_video.pool.shutdown()

if __name__=='__main__':main()
