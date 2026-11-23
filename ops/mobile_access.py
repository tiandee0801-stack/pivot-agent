#!/usr/bin/env python3
"""Start a paired, temporary HTTPS preview without exposing other local services."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]
OUTPUT=WORKSPACE/'output'/'Pivot-Demo-V1.1.3-2026-11-20'/'配对入口'
RUNTIME=Path.home()/'Library'/'Application Support'/'Dee'/'Pivot-Demo-v113-paired'
PYTHON=ROOT.parent/'stride-agent'/'local-ai'/'.venv'/'bin'/'python'
TUNNEL=WORKSPACE/'output'/'Pivot-MVP-2026-11-09'/'tools'/'cloudflared'
PORT=8898

def alive(pid):
    try: os.kill(pid,0); return True
    except (OSError,TypeError): return False

def write_private(path,text):
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(text)
    temp.chmod(0o600)
    temp.replace(path)

def healthy():
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/health',timeout=2) as res:
            result=json.load(res)
            return result.get('app')=='pivot-agent' and result.get('demoVersion')=='1.1.3'
    except Exception:
        return False

def rotate_logs():
    for path in RUNTIME.glob('*.log*'):
        if time.time()-path.stat().st_mtime>30*86400:
            path.unlink()
        elif path.suffix=='.log' and path.stat().st_size>5*1024*1024:
            path.replace(path.with_name(path.name+'.'+str(int(time.time()))))

def launch():
    os.umask(0o077)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    state_path=RUNTIME/'access.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if all(alive(state.get(k)) for k in ('supervisor','tunnel','server')) and healthy():
            print(json.dumps({'running':True,'url':state.get('url'),'entry':str(OUTPUT/'00-打开Pivot手机MVP.html')},ensure_ascii=False)); return
    if not TUNNEL.is_file(): raise SystemExit('cloudflared is not installed in the project tools folder')
    if healthy(): raise SystemExit(f'Port {PORT} already has a service.')
    rotate_logs()
    log=open(RUNTIME/'supervisor.log','a')
    proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--supervise'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    print(json.dumps({'starting':True,'supervisor':proc.pid,'statusFile':str(state_path)},ensure_ascii=False))

def supervise():
    os.umask(0o077)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    secret_path=RUNTIME/'pair-code.txt'
    if not secret_path.exists(): write_private(secret_path,secrets.token_urlsafe(12))
    code=secret_path.read_text().strip()
    tunnel_log=RUNTIME/'tunnel.log'; tunnel_log.write_text('')
    tunnel_output=open(tunnel_log,'a')
    tunnel=subprocess.Popen([str(TUNNEL),'tunnel','--no-autoupdate','--protocol','http2','--url',f'http://127.0.0.1:{PORT}'],stdin=subprocess.DEVNULL,stdout=tunnel_output,stderr=tunnel_output)
    server=None
    def shutdown(*args):
        if server and server.poll() is None: server.terminate()
        if tunnel.poll() is None: tunnel.terminate()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown); signal.signal(signal.SIGINT,shutdown)
    url=None
    for _ in range(100):
        if tunnel.poll() is not None: raise RuntimeError('HTTPS tunnel stopped; inspect local tunnel.log')
        match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',tunnel_log.read_text(errors='replace'))
        if match: url=match.group(); break
        time.sleep(.5)
    if not url:
        print('HTTPS address could not be created; inspect tunnel.log',flush=True)
        shutdown()
    env=os.environ.copy();env.pop('PIVOT_CATALOG_PREVIEW',None); env.update(PIVOT_PAIR_CODE=code,PIVOT_PUBLIC_ORIGIN=url)
    server_log=open(RUNTIME/'server.log','a')
    server=subprocess.Popen([str(PYTHON),'-u',str(ROOT/'server.py'),'--port',str(PORT),'--db',str(RUNTIME/'mobile.sqlite3')],env=env,stdin=subprocess.DEVNULL,stdout=server_log,stderr=server_log,cwd=ROOT)
    for _ in range(60):
        if server.poll() is not None: shutdown()
        if healthy(): break
        time.sleep(.5)
    else: shutdown()
    state={'supervisor':os.getpid(),'tunnel':tunnel.pid,'server':server.pid,'url':url,'port':PORT,'createdAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    write_private(RUNTIME/'access.json',json.dumps(state,ensure_ascii=False,indent=2))
    entry=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>打开 Pivot 换场</title><style>body{{margin:0;background:#080b09;color:#eef4eb;font:17px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:760px;margin:60px auto;padding:30px}}h1{{font-size:50px;line-height:1.1}}.green{{color:#c7ff4a}}.card{{background:#171d17;border:1px solid #2b3928;border-radius:24px;padding:28px;margin:24px 0}}a{{color:#c7ff4a;word-break:break-all}}code{{font-size:23px;user-select:all}}small{{color:#acb5a6}}.button{{display:inline-block;background:#c7ff4a;color:#111a06;text-decoration:none;border-radius:16px;padding:12px 24px;font-weight:700}}</style><main><p class="green">PIVOT · 换场</p><h1>把运动安排<br>接回你的生活。</h1><div class="card"><p>手机或电脑打开下面的地址，输入本页配对码即可。</p><a href="{html.escape(url)}" class="button" target="_blank" rel="noreferrer">打开 Pivot</a><p><a href="{html.escape(url)}">{html.escape(url)}</a></p><p>私人配对码<br><code>{html.escape(code)}</code></p><small>此页面只保存在你的电脑上，不在网站里。配对后可访问同一份个人资料，请只交给你信任的演示对象。</small></div><div class="card"><b>添加到手机桌面</b><p>iPhone 用 Safari 打开 → 分享 → 添加到主屏幕。Android 用 Chrome 打开 → 菜单 → 安装应用或添加到主屏幕。</p><b>先试这条流程</b><p>我的：填写目标并确认现有计划 → 今日：发起调整 → 确认保存 → 训练：上传弯举视频 → 回放并校正 → 保存训练记录 → 再次调整，查看记录引用。</p></div><p><small>这是使用本机算力的临时 HTTPS MVP。Mac 与连接进程需保持在线；重新启动手机入口会更换网址，配对码与数据保留。原本 8846 版本和资料不会被覆盖。不要将本页加入公开仓库。</small></p></main></html>'''
    OUTPUT.mkdir(parents=True,exist_ok=True)
    write_private(OUTPUT/'00-打开Pivot手机MVP.html',entry)
    while server.poll() is None and tunnel.poll() is None: time.sleep(2)
    shutdown()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--supervise',action='store_true');args=parser.parse_args()
    supervise() if args.supervise else launch()
