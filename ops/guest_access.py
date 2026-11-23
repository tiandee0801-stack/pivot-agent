#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated visitor PWA with supervised local or temporary HTTPS access."""
import argparse,html,json,os,re,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]
OUTPUT=WORKSPACE/'output'/'Pivot-Demo-V1.1.3-2026-11-20'
RUNTIME=Path.home()/'Library'/'Application Support'/'Dee'/'Pivot-Demo-v113'
PYTHON=ROOT.parent/'stride-agent'/'local-ai'/'.venv'/'bin'/'python'
TUNNEL=WORKSPACE/'output'/'Pivot-MVP-2026-11-09'/'tools'/'cloudflared'
PORT=int(os.environ.get('PIVOT_DEMO_PORT','8897'))
VERSION='1.1.3'
LOCAL_URL=f'http://127.0.0.1:{PORT}'
ENTRY=OUTPUT/'00-打开Pivot手机MVP.html'

def alive(pid):
 try:os.kill(pid,0);return True
 except (OSError,TypeError):return False

def private(path,text):
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+'.tmp');temp.write_text(text);temp.chmod(0o600);temp.replace(path)

def healthy(port=PORT):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:
   health=json.load(response)
   return health.get('app')=='pivot-agent' and health.get('demoVersion')==VERSION
 except Exception:return False

def port_available():
 with socket.socket() as probe:
  probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  try:
   probe.bind(('127.0.0.1',PORT))
  except OSError:
   return False
 return True

def launch(local):
 os.umask(0o077);RUNTIME.mkdir(parents=True,exist_ok=True)
 p=RUNTIME/'access.json'
 if p.exists():
  state=json.loads(p.read_text())
  components=('supervisor','server') if state.get('local') else ('supervisor','tunnel','server')
  if all(alive(state.get(k)) for k in components) and healthy(state.get('port',PORT)):
   if bool(state.get('local'))!=local:
    raise SystemExit(f'{PORT} 已有 V{VERSION} 服务，当前访问方式为 {state["url"]}。')
   print(json.dumps({'running':True,'url':state['url'],'entry':str(ENTRY)},ensure_ascii=False));return
 if not port_available():raise SystemExit(f'{PORT} 已有服务，请先核查本实例状态。')
 if not local and not TUNNEL.is_file():raise SystemExit('缺少已有的官方 cloudflared 工具。')
 command=[sys.executable,str(Path(__file__).resolve()),'--supervise']
 if local:command.append('--local')
 with open(RUNTIME/'supervisor.log','a') as log:
  proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
 print(json.dumps({'starting':True,'supervisor':proc.pid,'statusFile':str(p)},ensure_ascii=False))

def supervise(local):
 os.umask(0o077);RUNTIME.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
 if not port_available():raise SystemExit(f'{PORT} 已有服务。')
 tunnel=None
 server=None
 def shutdown(*_):
  if server and server.poll() is None:server.terminate()
  if tunnel and tunnel.poll() is None:tunnel.terminate()
  raise SystemExit(0)
 signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
 url=LOCAL_URL if local else None
 if not local:
  tunnel_log=RUNTIME/'tunnel.log'
  with open(tunnel_log,'w') as tunnel_out:
   tunnel=subprocess.Popen([str(TUNNEL),'tunnel','--no-autoupdate','--protocol','http2','--url',LOCAL_URL],stdin=subprocess.DEVNULL,stdout=tunnel_out,stderr=tunnel_out)
  for _ in range(100):
   if tunnel.poll() is not None:raise RuntimeError('HTTPS 进程停止，请查看本地日志。')
   match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',tunnel_log.read_text(errors='replace'))
   if match:url=match.group();break
   time.sleep(.5)
 if not url:shutdown()
 env=os.environ.copy();env.pop('PIVOT_CATALOG_PREVIEW',None);env.pop('PIVOT_PAIR_CODE',None);env.update(PIVOT_GUEST_MODE='1',PIVOT_PUBLIC_ORIGIN='' if local else url,PYTHONDONTWRITEBYTECODE='1')
 if local:env['PIVOT_CATALOG_PREVIEW']='1'
 with open(RUNTIME/'server.log','a') as server_log:
  server=subprocess.Popen([str(PYTHON),'-u',str(ROOT/'server.py'),'--port',str(PORT),'--db',str(RUNTIME/'base.sqlite3')],env=env,stdin=subprocess.DEVNULL,stdout=server_log,stderr=server_log,cwd=ROOT)
 for _ in range(90):
  if server.poll() is not None:shutdown()
  if healthy():break
  time.sleep(.5)
 else:shutdown()
 state={'supervisor':os.getpid(),'tunnel':tunnel.pid if tunnel else None,'server':server.pid,'url':url,'port':PORT,'local':local,'createdAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
 safe=html.escape(url)
 access_note=(
  '在这台 Mac 的浏览器中使用。'
  if local else 'iPhone 用 Safari 打开，选择「分享 → 添加到主屏幕」。Mac 需保持开机联网，临时网址重启后可能改变。'
 )
 entry=f'''<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pivot 换场 · Demo V{VERSION}</title>
<style>
body{{background:#070907;color:#f1f5e9;font:16px/1.8 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;margin:0}}
main{{max-width:720px;margin:40px auto;padding:24px}}
a{{color:#ccff00;overflow-wrap:anywhere}}
.card{{background:#1b201a;border:1px solid #42542b;padding:24px;border-radius:24px;margin:24px 0}}
.button{{display:inline-block;border-radius:16px;padding:12px 22px;background:#ccff00;color:#121900;text-decoration:none;font-weight:750}}
small{{color:#a1aa98}}
li{{margin:11px 0}}
</style>
<main>
<h1>Pivot 换场 · Demo V{VERSION}</h1>
<div class="card">
<a class="button" href="{safe}">打开 Demo</a>
<p><a href="{safe}">{safe}</a></p>
<small>{access_note} 每个浏览器有独立的示例空间。</small>
</div>
<ol>
<li>打开「训练」，按动作类别、器械或名称找动作。</li>
<li>打开场景模板，查看、编辑动作清单，再保存到计划。</li>
<li>记录本次多动作训练，在「历史」核对实际数据。</li>
</ol>
</main>
</html>'''
 private(ENTRY,entry)
 private(OUTPUT/('本机访问链接.txt' if local else '手机访问链接.txt'),url+'\n')
 private(RUNTIME/'access.json',json.dumps(state,ensure_ascii=False,indent=2))
 print('MVP ready '+url,flush=True)
 while server.poll() is None and (tunnel is None or tunnel.poll() is None):time.sleep(2)
 shutdown()

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--supervise',action='store_true')
 parser.add_argument('--local',action='store_true',help='只运行本机回环预览，禁用 HTTPS 隧道。')
 args=parser.parse_args()
 supervise(args.local) if args.supervise else launch(args.local)
