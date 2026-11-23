"""Private QA against local QuickPose reference GIFs; never serves reference media."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guest_spaces import GuestSpaces
from intent import LocalIntent
from mobile_backend import VideoManager, MEDIA_TOOLS
from server import PivotHandler

REFERENCES={
    'squat':'docs/v0.3/fitness-squat-counter.gif',
    'pushup':'docs/v0.5/fitness-push-up-counter.gif',
    'lateral_raise':'docs/v1.1.0/fitness-lateral-raises.gif',
    'overhead_press':'docs/v1.1.0/fitness-overhead-dumbbell-press.gif',
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quickpose-root',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pivot-reference-qa-') as temp:
        root=Path(temp);base=VideoManager(root/'base.sqlite3');spaces=GuestSpaces(root/'visitors')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(PivotHandler,
            db_path=str(root/'base.sqlite3'),video=base,model=LocalIntent(enabled=False),pairing=spaces))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin='http://127.0.0.1:'+str(server.server_port)
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,data=None,method=None,headers=None):
            req=urllib.request.Request(origin+path,data=data,method=method,headers=headers or {})
            with client.open(req,timeout=60) as response:return response.status,json.loads(response.read())
        report={'scope':'four matching reference clips through real HTTP upload and RTMPose; single-source smoke, not accuracy validation',
            'source':'https://github.com/quickpose/quickpose-ios-sdk','actions':[]}
        try:
            call('/api/state')
            for exercise,relative in REFERENCES.items():
                target=root/(exercise+'.mp4')
                converted=subprocess.run([str(MEDIA_TOOLS/'ffmpeg'),'-nostdin','-v','error','-i',str(args.quickpose_root/relative),
                    '-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-y',str(target)],
                    capture_output=True,timeout=30)
                assert converted.returncode==0,converted.stderr.decode(errors='replace')
                status,job=call('/api/video?side=left&exercise='+exercise,target.read_bytes(),'POST',{'Content-Type':'video/mp4'})
                assert status==202
                ident=job['jobId'];started=time.monotonic()
                while True:
                    _,job=call('/api/jobs/'+ident)
                    if job['status'] in ('done','error'):break
                    assert time.monotonic()-started<260
                    time.sleep(.5)
                assert job['status']=='done',job
                result=job['result']
                assert result['exercise']==exercise and result['mode']=='rtmpose-onnx' and result['frames']
                report['actions'].append({'exercise':exercise,'sourceFile':relative,'quality':result['quality'],
                    'count':result['count'],'validRatio':result['validRatio'],'qualityReasons':result['qualityReasons'],
                    'seconds':round(time.monotonic()-started,2)})
                # Keep only aggregate angles in the private QA report to diagnose
                # coverage without retaining the reference video or skeleton.
                angles=[frame['angle'] for frame in result['frames'] if frame['angle'] is not None]
                report['actions'][-1]['observedAngleRange']=[min(angles),max(angles)] if angles else None
                print(json.dumps(report['actions'][-1],ensure_ascii=False),flush=True)
                call('/api/jobs/'+ident,method='DELETE')
            report['passed']=all(a['quality']=='usable' and isinstance(a['count'],int) and a['count']>0 for a in report['actions'])
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            if not report['passed']:raise SystemExit('At least one reference clip requires review; see report.')
        finally:
            server.shutdown();server.server_close();base.pool.shutdown()
            for db,manager in spaces.managers.values():manager.pool.shutdown()


if __name__=='__main__':main()
