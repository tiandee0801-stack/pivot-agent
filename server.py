"""Pivot single-user PWA adapter. Loopback by default; paired HTTPS only when configured."""
from __future__ import annotations
import argparse
import json
import os
import re
import socket
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import urlsplit,parse_qs
from uuid import uuid4
from engine import dispatch, RequestError
from intent import LocalIntent
from mobile_backend import VideoManager, Pairing, ID_RE
from guest_spaces import GuestSpaces
import training_catalog
from workout import ROUTES as WORKOUT_ROUTES

ROOT=Path(__file__).resolve().parent
WEB_ROOT=ROOT/'web'
DEMO_ROOT=WEB_ROOT/'assets'/'demos'
DEFAULT_DB=Path.home()/'Library'/'Application Support'/'Dee'/'Pivot-Demo-v113'/'base.sqlite3'
DEMO_VERSION='1.1.3'
ERROR_FORMAT_HEADER='X-Pivot-Error-Format'
MIME={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8',
      '.svg':'image/svg+xml','.woff2':'font/woff2','.png':'image/png','.webp':'image/webp','.jpg':'image/jpeg',
      '.ico':'image/x-icon','.webmanifest':'application/manifest+json','.json':'application/json'}
ROUTES={'/api/tasks','/api/answer','/api/confirm','/api/confirm/check','/api/keep','/api/cancel','/api/feedback','/api/settings',
        '/api/device','/api/wearable','/api/wearable/disconnect','/api/reset','/api/events','/api/plan','/api/alternatives','/api/sessions','/api/sessions/update'} | WORKOUT_ROUTES

class PivotHandler(BaseHTTPRequestHandler):
    def __init__(self,*args,db_path,model,video,pairing,**kwargs):
        self.db_path,self.model,self.video,self.pairing=db_path,model,video,pairing
        super().__init__(*args,**kwargs)
    def setup(self):
        super().setup()
        self.connection.settimeout(60)
    def log_message(self,*_):
        pass
    def send_body(self,status,data,mime,headers=None):
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        if getattr(self,'new_guest_cookie',None):
            self.send_header('Set-Cookie',self.new_guest_cookie)
        for key,value in (headers or {}).items():
            self.send_header(key,value)
        self.end_headers()
        if self.command!='HEAD':
            try:
                self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                pass
    def send_json(self,status,value,headers=None):
        self.send_body(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8',headers)
    def structured_errors(self):
        return self.headers.get(ERROR_FORMAT_HEADER,'').strip().lower()=='structured'
    def fail(self,status,code,msg):
        if self.structured_errors():
            result={'error':{'code':code,'message':msg}}
        else:
            result={'code':code,'error':msg}
        self.send_json(status,result,{'Vary':ERROR_FORMAT_HEADER})
    def send_error(self,code,message=None,explain=None):
        # The HTTP parser also generates errors before any route is called.
        if getattr(self,'headers',None) and getattr(self,'path','').startswith('/api/') and self.structured_errors():
            error_code,text=('method_not_allowed','不支持此请求方式。') if code==501 else ('invalid_request','请求格式无效。')
            return self.fail(code,error_code,text)
        return super().send_error(code,message,explain)
    def request_allowed(self):
        port=self.server.server_port
        allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        origins={f'http://127.0.0.1:{port}',f'http://localhost:{port}'}
        if self.pairing.origin:
            allowed.add(urlsplit(self.pairing.origin).netloc.lower())
            origins.add(self.pairing.origin)
        host=self.headers.get('Host','').lower()
        if host not in allowed:
            self.fail(403,'host_denied','请从已配置的 Pivot 地址打开。')
            return False
        if self.command not in ('GET','HEAD'):
            origin=self.headers.get('Origin')
            if (origin is not None and origin not in origins) or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.fail(403,'foreign_origin','请在 Pivot 页面内操作。')
                return False
        return True
    def require_auth(self):
        if not (getattr(self.pairing,'guest',False) or self.pairing.authenticated(self.headers.get('Cookie'))):
            self.fail(401,'pair_required','请先输入配对码连接你的 Pivot。')
            return False
        return True
    def execute(self,method,path,data):
        status,result=dispatch(self.db_path,method,path,data)
        if status>=400:
            return self.fail(status,result['code'],result['error'])
        result['model']=self.model.info()
        result['vision']=self.video.info()
        extra={'Content-Disposition':'attachment; filename="pivot-records.json"'} if path=='/api/export' else None
        self.send_json(status,result,extra)
    def guard(self,func):
        try:
            if self.request_allowed():
                if getattr(self.pairing,'guest',False):
                    token=self.pairing.token(self.headers.get('Cookie'))
                    if not token:
                        token=self.pairing.create()
                        self.new_guest_cookie=self.pairing.cookie(token)
                    self.db_path,self.video=self.pairing.workspace(token)
                func()
        except RequestError as exc:
            self.fail(exc.status,exc.code,str(exc))
        except (socket.timeout,TimeoutError):
            self.fail(408,'timeout','请求超时，操作结果请在历史记录中核对。')
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception as exc:
            print('Pivot request failure: '+type(exc).__name__,flush=True)
            self.fail(500,'service_error','暂时无法核对操作结果，请刷新查看最新记录。')
    def do_GET(self):
        self.guard(self.get)
    do_HEAD=do_GET
    def get(self):
        self.video.cleanup_expired()
        path=urlsplit(self.path).path
        if path=='/api/health':
            return self.send_json(200,{'app':'pivot-agent','demoVersion':DEMO_VERSION,'model':self.model.info(),'vision':self.video.info(),'authRequired':bool(self.pairing.code)})
        if path=='/api/auth':
            return self.send_json(200,{'authenticated':getattr(self.pairing,'guest',False) or self.pairing.authenticated(self.headers.get('Cookie')),'pairingRequired':bool(self.pairing.code),'guestSpace':getattr(self.pairing,'guest',False)})
        if path.startswith(('/api/','/media/')):
            if not self.require_auth():
                return
            if path in ('/api/state','/api/export') or path.startswith('/api/operations/'):
                return self.execute('GET',path,{})
            if path.startswith('/api/jobs/'):
                return self.send_json(200,self.video.get(path.rsplit('/',1)[-1]))
            if path.startswith('/media/'):
                return self.media(path)
            return self.fail(404,'not_found','未找到接口。')
        name='index.html' if path=='/' else path.lstrip('/')
        resource=(WEB_ROOT/name).resolve()
        if DEMO_ROOT in resource.parents and resource.suffix=='.mp4' and training_catalog.enabled() and resource.is_file():
            return self.send_video(resource)
        if WEB_ROOT not in resource.parents or resource.suffix.lower() not in MIME or not resource.is_file():
            return self.fail(404,'not_found','未找到页面。')
        self.send_body(200,resource.read_bytes(),MIME[resource.suffix.lower()])
    def media(self,path):
        name=path.rsplit('/',1)[-1]
        if not re.fullmatch(r'[0-9a-f]{32}\.mp4',name):
            return self.fail(404,'not_found','视频不存在。')
        job=self.video.get(name[:-4])
        resource=self.video.media/name
        if job['status']!='done' or not resource.is_file():
            return self.fail(404,'not_found','视频已删除或尚未完成处理。')
        return self.send_video(resource)
    def send_video(self,resource):
        size=resource.stat().st_size
        start,end,status=0,size-1,200
        value=self.headers.get('Range')
        if value:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
            if not match or not any(match.groups()):
                return self.send_body(416,b'','video/mp4',{'Content-Range':f'bytes */{size}'})
            first,last=match.groups()
            if first:
                start=int(first)
                end=min(int(last),size-1) if last else size-1
            else:
                count=int(last)
                if not count:
                    return self.send_body(416,b'','video/mp4',{'Content-Range':f'bytes */{size}'})
                start=max(0,size-count)
            if start>=size or start>end:
                return self.send_body(416,b'','video/mp4',{'Content-Range':f'bytes */{size}'})
            status=206
        self.send_response(status)
        self.send_header('Content-Type','video/mp4')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if status==206:
            self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command=='HEAD':
            return
        with resource.open('rb') as source:
            source.seek(start)
            remaining=end-start+1
            while remaining:
                chunk=source.read(min(65536,remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining-=len(chunk)
    def read_json(self):
        if self.headers.get_content_type()!='application/json':
            raise RequestError('请求需要 JSON 格式。','unsupported_type',415)
        try:
            size=int(self.headers.get('Content-Length','0'))
        except ValueError:
            size=-1
        if not 1<=size<=32768:
            raise RequestError('请求为空或内容过长。','bad_size',413)
        try:
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError
        except (ValueError,UnicodeDecodeError):
            raise RequestError('无法读取请求内容。','bad_json')
        return {k:v for k,v in data.items() if not k.startswith('_')}
    def interpret_turn(self,path,data):
        value=data.get('input' if path=='/api/tasks' else 'text')
        if not isinstance(value,str) or len(value)>500 or not value.strip():
            return  # The engine returns the existing input validation error.
        if path=='/api/tasks' and data.get('entry')=='quick':
            source='structured_rules'
            diagnostics={'reason':None,'readiness':'bypassed','attempts':0,'parseMs':0}
        else:
            result=self.model.interpret(value)
            if result.intent is not None:
                source='model'
                data['_intent']=result.intent
            else:
                source='fallback_rules'
            diagnostics={'reason':result.reason,'readiness':result.readiness,
                         'attempts':result.attempts,'parseMs':result.elapsed_ms}
        data['_interpretation']={'source':source,'requestId':uuid4().hex}
        data['_intent_diagnostics']=diagnostics
    def do_POST(self):
        self.guard(self.post)
    def post(self):
        parsed=urlsplit(self.path)
        path=parsed.path
        if path=='/api/auth/pair':
            data=self.read_json()
            token=self.pairing.pair(data.get('code'),self.client_address[0])
            return self.send_json(200,{'authenticated':True},{'Set-Cookie':self.pairing.cookie(token)})
        if path=='/api/auth/logout':
            self.read_json()
            self.pairing.logout(self.headers.get('Cookie'))
            return self.send_json(200,{'authenticated':not bool(self.pairing.code)},{'Set-Cookie':self.pairing.cookie('')})
        if not self.require_auth():
            return
        if path=='/api/wearable/import':
            from wearable import parse_export,MAX_IMPORT
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError:size=0
            if not 1<=size<=MAX_IMPORT: raise RequestError('请选择 100 MB 以内的健康导出文件。','import_size',413)
            data=parse_export(self.rfile.read(size),'health-export')
            return self.execute('POST','/api/wearable',{'_parsed':data})
        if path=='/api/video':
            mime=self.headers.get_content_type()
            if not (mime.startswith('video/') or mime=='application/octet-stream'):
                raise RequestError('请选择视频文件。','unsupported_type',415)
            try:
                size=int(self.headers.get('Content-Length','0'))
            except ValueError:
                size=0
            side=parse_qs(parsed.query).get('side',['left'])[0]
            return self.send_json(202,self.video.upload(self.rfile,size,side,parse_qs(parsed.query).get('exercise',['bicep_curl'])[0]))
        if path not in ROUTES:
            return self.fail(404,'not_found','未找到操作。')
        data=self.read_json()
        if path=='/api/wearable' and 'parsed' in data: raise RequestError('请通过文件导入入口提交健康记录。')
        if path in ('/api/tasks','/api/answer'):
            self.interpret_turn(path,data)
        if path=='/api/reset':
            if not self.video.lock.acquire(blocking=False):
                raise RequestError('视频处理中，结束后可以清空。','video_busy',409)
            try:
                self.execute('POST',path,data)
                for folder in (self.video.media,self.video.jobs):
                    for file in folder.iterdir():
                        if file.is_file():
                            file.unlink(missing_ok=True)
            finally:
                self.video.lock.release()
        else:
            self.execute('POST',path,data)
    def do_DELETE(self):
        self.guard(self.delete)
    def delete(self):
        if not self.require_auth():
            return
        path=urlsplit(self.path).path
        if path.startswith('/api/jobs/'):
            self.video.delete(path.rsplit('/',1)[-1])
            return self.execute('GET','/api/state',{})
        if path.startswith('/api/sessions/'):
            return self.execute('DELETE',path,{})
        self.fail(404,'not_found','未找到操作。')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8897)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--rules-only',action='store_true')
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if os.environ.get('PIVOT_CATALOG_PREVIEW') == '1':
        if args.host not in ('127.0.0.1','localhost','::1') or os.environ.get('PIVOT_PUBLIC_ORIGIN'):
            parser.error('篮球动作库待审核，预览仅限本机回环访问。')
        training_catalog.catalog()
    os.umask(0o077)
    pairing=GuestSpaces(args.db.parent/'visitor-spaces',os.environ.get('PIVOT_PUBLIC_ORIGIN','')) if os.environ.get('PIVOT_GUEST_MODE')=='1' else Pairing(os.environ.get('PIVOT_PAIR_CODE',''),os.environ.get('PIVOT_PUBLIC_ORIGIN',''))
    if args.host not in ('127.0.0.1','localhost','::1') and not (pairing.origin and (pairing.code or getattr(pairing,'guest',False))):
        parser.error('Network binding requires PIVOT_PAIR_CODE and HTTPS PIVOT_PUBLIC_ORIGIN; default stays local.')
    args.db.parent.mkdir(parents=True,exist_ok=True)
    dispatch(str(args.db),'GET','/api/state',{})
    video=VideoManager(args.db)
    model=LocalIntent(enabled=not args.rules_only)
    factory=partial(PivotHandler,db_path=str(args.db),model=model,video=video,pairing=pairing)
    with ThreadingHTTPServer((args.host,args.port),factory) as server:
        print(f'Pivot mobile MVP http://127.0.0.1:{server.server_port}/',flush=True)
        if args.open:
            Timer(.3,webbrowser.open,args=(f'http://127.0.0.1:{server.server_port}/',)).start()
        try:
            server.serve_forever()
        finally:
            video.pool.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':
    main()
