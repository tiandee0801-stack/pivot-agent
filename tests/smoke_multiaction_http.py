"""Run every exercise route on a known curl clip; this is not 5-action accuracy validation."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import dispatch
from guest_spaces import GuestSpaces
from intent import LocalIntent
from mobile_backend import VideoManager
from server import PivotHandler
from video_engine.exercises import EXERCISES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--curl-input',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pivot-multiaction-') as temp:
        root=Path(temp);base=VideoManager(root/'base.sqlite3')
        spaces=GuestSpaces(root/'visitors')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(PivotHandler,
            db_path=str(root/'base.sqlite3'),video=base,model=LocalIntent(enabled=False),pairing=spaces))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin='http://127.0.0.1:'+str(server.server_port)
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,data=None,method=None,headers=None):
            req=urllib.request.Request(origin+path,data=data,method=method,headers=headers or {})
            with client.open(req,timeout=60) as response:
                return response.status,json.loads(response.read())
        report={'passed':False,'inputType':'previously checked single-person bicep curl clip',
            'scope':'all five HTTP upload/model routes and negative action checks; not accuracy for other movements',
            'actions':[]}
        try:
            # State allocates the browser's private space without an access code.
            call('/api/state')
            body=args.curl_input.read_bytes()
            for exercise in EXERCISES:
                status,job=call('/api/video?side=left&exercise='+exercise,body,'POST',{'Content-Type':'video/mp4'})
                assert status==202
                ident=job['jobId'];started=time.monotonic()
                while True:
                    _,job=call('/api/jobs/'+ident)
                    if job['status'] in ('done','error'):break
                    assert time.monotonic()-started<260
                    time.sleep(.5)
                assert job['status']=='done',job
                result=job['result']
                assert result['exercise']==exercise and result['mode']=='rtmpose-onnx'
                assert result['frames'] and result['quality'] in ('usable','insufficient')
                if exercise=='bicep_curl':assert result['quality']=='usable' and result['count']==4,result
                else:assert result['count'] in (None,0),(exercise,result['count'])
                report['actions'].append({'exercise':exercise,'status':'done','quality':result['quality'],
                    'count':result['count'],'validRatio':result['validRatio'],
                    'seconds':round(time.monotonic()-started,2)})
                call('/api/jobs/'+ident,method='DELETE')
            report['passed']=True
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            server.shutdown();server.server_close();base.pool.shutdown()
            for db,manager in spaces.managers.values():manager.pool.shutdown()


if __name__=='__main__':main()
