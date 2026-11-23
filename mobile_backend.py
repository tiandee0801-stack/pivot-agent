"""Bounded local video jobs, pairing sessions and normalized media storage."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlsplit
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import uuid
from engine import RequestError, bootstrap, encode, stamp
import mobile_records as records
import analytics
from video_engine.exercises import EXERCISES, public_exercises

ROOT=Path(__file__).resolve().parent
GYM=Path(os.environ.get('PIVOT_GYM_ROOT','/Users/Admin/Documents/运动健身资料/Good-GYM-master'))
MEDIA_TOOLS=Path(os.environ.get('PIVOT_MEDIA_TOOLS','/Users/Admin/Documents/运动健身资料/openpose-master/.native/bin'))
PYTHON_VISION=Path(os.environ.get('PIVOT_VISION_PYTHON',str(GYM/'.venv/bin/python')))
MAX_VIDEO=60*1024*1024
# Only file containers, never playlist/concat/network demuxers. MOV external drefs remain disabled.
SAFE_MEDIA_FLAGS=['-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm']
MOV_MEDIA_FLAGS=['-enable_drefs','0']
ID_RE=re.compile(r'^[0-9a-f]{32}$')

class ApiError(RequestError):
    def __init__(self,status,message):
        super().__init__(message,'video_error',status)
        self.message=message

class Pairing:
    def __init__(self,code='',origin=''):
        self.code=code
        self.origin=origin.rstrip('/')
        self.sessions={}
        self.attempts={}
        self.lock=threading.Lock()
        if code and len(code)<8:
            raise ValueError('PIVOT_PAIR_CODE must contain at least 8 characters')
        if origin and (urlsplit(origin).scheme!='https' or not code):
            raise ValueError('Public origin requires HTTPS and a pairing code')
    def authenticated(self,cookie):
        if not self.code:
            return True
        token=self.token(cookie)
        with self.lock:
            return self.sessions.get(hashlib.sha256(token.encode()).hexdigest(),0)>time.time()
    @staticmethod
    def token(cookie):
        from http.cookies import SimpleCookie
        try:
            parsed=SimpleCookie(cookie or '')
            return parsed['pivot_session'].value if 'pivot_session' in parsed else ''
        except Exception:
            return ''
    def pair(self,code,peer):
        if not self.code:
            return ''
        with self.lock:
            now=time.time()
            history=[t for t in self.attempts.get(peer,[]) if now-t<60]
            if len(history)>=10:
                raise RequestError('尝试过于频繁，请一分钟后重试。','rate_limit',429)
            history.append(now)
            self.attempts[peer]=history
            if not isinstance(code,str) or not hmac.compare_digest(code.encode(),self.code.encode()):
                raise RequestError('配对码不正确。','invalid_code',401)
            token=secrets.token_urlsafe(32)
            self.sessions={k:v for k,v in self.sessions.items() if v>now}
            self.sessions[hashlib.sha256(token.encode()).hexdigest()]=now+7*86400
            return token
    def logout(self,cookie):
        token=self.token(cookie)
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)
    def cookie(self,token):
        return 'pivot_session='+token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age='+('604800' if token else '0')+('; Secure' if self.origin else '')


class VideoManager:
    def __init__(self,db_path):
        # The inference subprocess runs from ROOT. Keep database/media paths
        # absolute so a relative --db cannot silently break its input/output.
        self.db_path=str(Path(db_path).expanduser().resolve())
        self.data=Path(self.db_path).with_suffix('.assets')
        self.media=self.data/'media'
        self.jobs=self.data/'jobs'
        self.media.mkdir(parents=True,exist_ok=True)
        self.jobs.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock()
        self.last_cleanup=0
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pivot-video')
        with self.database() as db:
            bootstrap(db)
            for job in records.all_records(db,'video_jobs'):
                if job['status'] in ('queued','running'):
                    job.update(status='error',error='上次分析被中断，请重新上传。')
                    db.execute('UPDATE video_jobs SET data=? WHERE id=?',(encode(job),job['jobId']))
                    for ext in ('.upload','.mp4'):
                        (self.media/(job['jobId']+ext)).unlink(missing_ok=True)
        self.cleanup_expired()
    def database(self):
        return sqlite3.connect(self.db_path,timeout=10)
    def info(self):
        available=all(p.is_file() for p in (PYTHON_VISION,MEDIA_TOOLS/'ffmpeg',MEDIA_TOOLS/'ffprobe',ROOT/'video_engine/vision.py',
                  GYM/'models/yolox_nano_8xb8-300e_humanart-40f6f0d0.onnx',
                  GYM/'models/rtmpose-s_simcc-body7_pt-body7_420e-256x192-acd4a1ef_20230504.onnx'))
        return {'available':available,'label':'RTMPose · 多动作训练分析','actions':list(EXERCISES),'exercises':public_exercises()}
    def get(self,ident):
        if not ID_RE.fullmatch(ident):
            raise RequestError('视频任务不存在。','not_found',404)
        with self.database() as db:
            job=records.get_record(db,'video_jobs',ident)
        progress=100 if job['status']=='done' else 0
        if job['status']=='running':
            try:
                val=json.loads((self.jobs/f'{ident}.progress.json').read_text()).get('progress',0)
                progress=max(0,min(99,float(val)))
            except (ValueError,OSError,TypeError):
                pass
        job['progress']=progress
        return job
    def put(self,job):
        with self.database() as db:
            db.execute('UPDATE video_jobs SET data=? WHERE id=?',(encode(job),job['jobId']))
    def upload(self,stream,size,side,exercise="bicep_curl"):
        if exercise not in EXERCISES:
            raise RequestError("不支持这个训练动作。")
        if side not in ('left','right'):
            raise RequestError('请选择身体左侧或右侧。')
        if not self.info()['available']:
            raise RequestError('本机视频识别依赖尚未就绪。','vision_unavailable',503)
        if not 1<=size<=MAX_VIDEO:
            raise RequestError('视频为空或超过 60 MiB。','video_size',413)
        if not self.lock.acquire(blocking=False):
            raise RequestError('上一段视频正在分析，请稍候。','video_busy',429)
        ident=uuid.uuid4().hex
        raw=self.media/f'{ident}.upload'
        try:
            with self.database() as db:
                if db.execute('SELECT count(*) FROM video_jobs').fetchone()[0]>=30:
                    raise RequestError('本机已保存 30 段视频，请删除旧视频后再上传。','storage_limit',409)
            remaining=size
            with raw.open('wb') as out:
                while remaining:
                    chunk=stream.read(min(65536,remaining))
                    if not chunk:
                        raise RequestError('上传中断，请重新上传。','upload_incomplete',400)
                    out.write(chunk)
                    remaining-=len(chunk)
            job={'jobId':ident,'createdAt':stamp(),'status':'queued','exercise':exercise,'exerciseName':EXERCISES[exercise]['name'],'side':side,'progress':0,'error':None}
            with self.database() as db:
                db.execute('INSERT INTO video_jobs VALUES(?,?)',(ident,encode(job)))
                analytics.record(db,'video_submitted',{'jobId':ident,'status':'queued'})
            self.pool.submit(self.analyze,job)
            return {'jobId':ident,'status':'queued'}
        except Exception:
            raw.unlink(missing_ok=True)
            self.lock.release()
            raise
    def analyze(self,job):
        ident=job['jobId']
        raw=self.media/f'{ident}.upload'
        movie=self.media/f'{ident}.mp4'
        result_file=self.jobs/f'{ident}.json'
        try:
            job['status']='running'
            self.put(job)
            normalize_video(raw,movie)
            raw.unlink(missing_ok=True)
            process=subprocess.run([str(PYTHON_VISION),str(ROOT/'video_engine/vision.py'),'--input',str(movie),
                '--output',str(result_file),'--side',job['side'],'--exercise',job.get('exercise','bicep_curl')],cwd=ROOT,capture_output=True,timeout=240)
            if process.returncode or not result_file.is_file():
                raise ApiError(502,'视频识别未完成，请检查画面并重试。')
            result=json.loads(result_file.read_text())
            if result.get('quality') not in ('usable','insufficient') or not isinstance(result.get('frames'),list):
                raise ApiError(502,'分析结果格式不正确，没有生成替代计数。')
            if result['quality']=='insufficient':
                result['count']=None
            result['sourceUrl']=f'/media/{ident}.mp4'
            job.update(status='done',result=result,error=None,progress=100)
        except subprocess.TimeoutExpired:
            job.update(status='error',error='分析超时，请使用更短、更清晰的视频。')
        except RequestError as exc:
            job.update(status='error',error=str(exc))
        except Exception:
            job.update(status='error',error='本次分析失败，没有生成替代计数。')
        finally:
            try:
                self.put(job)
                with self.database() as db:
                    analytics.record(db,'video_finished',{'jobId':ident,'status':job['status'],
                        'quality':job.get('result',{}).get('quality'),'durationSeconds':job.get('result',{}).get('duration'),
                        'result':'success' if job['status']=='done' else 'failed'})
            finally:
                try:
                    raw.unlink(missing_ok=True)
                    if job['status']=='error':
                        movie.unlink(missing_ok=True)
                    result_file.unlink(missing_ok=True)
                finally:
                    self.lock.release()
    def cleanup_expired(self):
        if time.time()-self.last_cleanup<600 or not self.lock.acquire(blocking=False):
            return
        try:
            expired=[]
            cutoff=datetime.now().astimezone()-timedelta(days=7)
            with self.database() as db:
                db.execute('BEGIN IMMEDIATE')
                for job in records.all_records(db,'video_jobs'):
                    try:
                        created=datetime.fromisoformat(job.get('createdAt',''))
                    except (ValueError,TypeError):
                        continue
                    if created.tzinfo is None:
                        created=created.astimezone()
                    if created<cutoff and job.get('status') not in ('queued','running'):
                        ident=job['jobId']
                        expired.append(ident)
                        if job.get('result'):
                            job['result'].pop('sourceUrl',None)
                        job['mediaDeleted']=True
                        job['mediaDeletionReason']='retention_expired'
                        db.execute('UPDATE video_jobs SET data=? WHERE id=?',(encode(job),ident))
                changed=False
                for session in records.all_records(db,'sessions'):
                    if session.get('videoJobId') in expired and session.get('observation'):
                        if session['observation'].pop('sourceUrl',None) is not None:
                            changed=True
                        session['mediaDeleted']=True
                        db.execute('UPDATE sessions SET data=? WHERE id=?',(encode(session),session['id']))
                if changed:
                    ctx=bootstrap(db)
                    records.refresh_context(db,ctx)
                    db.execute('UPDATE workspace SET data=? WHERE id=1',(encode(ctx),))
            for ident in expired:
                for folder in (self.media,self.jobs):
                    for path in folder.glob(ident+'.*'):
                        path.unlink(missing_ok=True)
            self.last_cleanup=time.time()
        finally:
            self.lock.release()
    def delete(self,ident):
        # Mutations share the video lock: reset cannot race a new upload.
        if not self.lock.acquire(blocking=False):
            raise RequestError('视频分析中，结束后可以删除。','video_busy',409)
        try:
            with self.database() as db:
                db.execute('BEGIN IMMEDIATE')
                job=records.get_record(db,'video_jobs',ident)
                if job['status'] in ('queued','running'):
                    raise RequestError('视频分析中。','video_busy',409)
                db.execute('DELETE FROM video_jobs WHERE id=?',(ident,))
                for session in records.all_records(db,'sessions'):
                    if session.get('videoJobId')==ident and session.get('observation'):
                        session['observation'].pop('sourceUrl',None)
                        session['mediaDeleted']=True
                        db.execute('UPDATE sessions SET data=? WHERE id=?',(encode(session),session['id']))
                ctx=bootstrap(db)
                records.refresh_context(db,ctx)
                db.execute('UPDATE workspace SET data=? WHERE id=1',(encode(ctx),))
            for folder in (self.media,self.jobs):
                for path in folder.glob(ident+'.*'):
                    path.unlink(missing_ok=True)
        finally:
            self.lock.release()


def normalize_video(source, target):
    """Inspect before conversion; auto-rotate and strip audio for predictable playback."""
    probe = subprocess.run([str(MEDIA_TOOLS/'ffprobe'), *SAFE_MEDIA_FLAGS, *MOV_MEDIA_FLAGS, '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(source)], capture_output=True, text=True, timeout=12)
    try:
        meta = json.loads(probe.stdout)
        if probe.returncode or not set(meta.get('format',{}).get('format_name','').split(',')) & {'mov','matroska','webm'}:
            raise ValueError()
        stream = next(s for s in meta['streams'] if s.get('codec_type') == 'video')
        raw_duration = meta.get('format', {}).get('duration', stream.get('duration'))
        if raw_duration in (None, 'N/A', ''):
            # MediaRecorder's streaming WebM has no duration header. Inspect at
            # most 46 seconds of packet timestamps, then verify the final MP4.
            packets = subprocess.run([str(MEDIA_TOOLS/'ffprobe'), *SAFE_MEDIA_FLAGS, *MOV_MEDIA_FLAGS, '-v', 'error',
                '-select_streams', 'v:0', '-read_intervals', '%+46',
                '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', str(source)],
                capture_output=True, text=True, timeout=12)
            stamps = [(float(p['pts_time']), float(p.get('duration_time', 0)))
                      for p in json.loads(packets.stdout).get('packets', [])]
            if not stamps or any(not math.isfinite(x) for pair in stamps for x in pair):
                raise ValueError()
            duration = max(t + max(d, 0) for t,d in stamps) - min(t for t,d in stamps)
        else:
            duration = float(raw_duration)
        w,h = int(stream['width']), int(stream['height'])
        if not (0.3 <= duration <= 45.001 and 16 <= w <= 4096 and 16 <= h <= 4096 and w*h <= 13_000_000):
            raise ValueError()
    except (ValueError, KeyError, StopIteration, TypeError):
        raise ApiError(422, '视频无法读取或超出范围。请上传 0.3–45 秒、最高 4K 的单人视频。')
    rotation = float(stream.get('tags', {}).get('rotate', 0))
    for side in stream.get('side_data_list', []):
        if 'rotation' in side:
            rotation = float(side['rotation'])
    copy_compatible = (stream.get('codec_name') == 'h264' and stream.get('pix_fmt') == 'yuv420p'
                       and max(w,h) <= 1280 and rotation % 360 == 0)
    command = [str(MEDIA_TOOLS/'ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
               *SAFE_MEDIA_FLAGS, *(MOV_MEDIA_FLAGS if 'mov' in meta.get('format',{}).get('format_name','').split(',') else []), '-i', str(source), '-t', '46', '-map', '0:v:0', '-an', '-sn', '-dn', '-map_metadata', '-1']
    if copy_compatible:
        # Preserve decoded pixels and original cadence for pose measurements.
        command += ['-c:v', 'copy']
    else:
        command += ['-vf', "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                    '-vsync','0','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p']
    command += ['-movflags','+faststart',str(target)]
    converted = subprocess.run(command, capture_output=True, timeout=90)
    if converted.returncode or not target.is_file():
        raise ApiError(422, '视频转换失败，请换用 MP4 视频。')
    checked = subprocess.run([str(MEDIA_TOOLS/'ffprobe'), *SAFE_MEDIA_FLAGS, *MOV_MEDIA_FLAGS, '-v', 'error', '-show_entries',
                              'format=duration', '-of', 'json', str(target)],
                              capture_output=True, text=True, timeout=12)
    try:
        final_duration = float(json.loads(checked.stdout)['format']['duration'])
        if not 0.3 <= final_duration <= 45.001:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        target.unlink(missing_ok=True)
        raise ApiError(422, '视频时长超出范围，请录制或上传 0.3–45 秒的视频。')
